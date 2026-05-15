"""server_renderer — Python → Node.js subprocess 통합 (ADR-0018 Stage F2).

F2-b: `render_annotations_html_via_node()` 함수가 Python에서 Node.js CLI
(`apps/render/src/bin.ts`)를 subprocess로 호출해 Tiptap server-side HTML 을
반환한다.

통합 방식 결정 (subprocess):
  - subprocess: Python → `jiti src/bin.ts` 호출. 추가 프로세스 관리 불필요.
    Node.js + jiti 콜드 스타트 ~200ms (jsdom + Tiptap import).
  - HTTP 마이크로서비스: RTT 10~50ms + 별도 프로세스 관리 필요.
  - subprocess 채택 이유: 배포 복잡도 감소 (별 서비스 불필요), preview/PDF export
    각자 독립 호출, Playwright 시간이 지배적인 PDF export 에서 overhead 미미.
  - 한계: 매 preview 요청마다 Node.js 프로세스 boot ~200ms 추가.
    트래픽이 증가하면 HTTP 서비스 전환 권장 (Python wrapper 교체만으로 가능).
  - jiti 선택 이유: @english-worksheet-tool/editor 패키지가 TypeScript source를
    exports하므로 Node.js 런타임에서 직접 실행 불가. jiti는 workspace TypeScript
    source를 런타임 트랜스파일해 별도 빌드 단계 불필요.

환경변수:
  - NODE_BIN: node 바이너리 경로 (default: "node")
  - JITI_BIN: jiti 바이너리 경로 (default: apps/render/node_modules/.bin/jiti)
  - SERVER_RENDERER_PATH: bin.ts 경로
    (default: apps/render/src/bin.ts — jiti 실행 기준)
  - LEGACY_ANNOTATION_RENDERER: "true" 이면 annotation_html.py fallback 사용
  - SERVER_RENDERER_TIMEOUT: subprocess 타임아웃 초 (default: 30)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from shared.schemas.annotation import SyntaxAnnotation
from shared.schemas.passage import Passage

logger = logging.getLogger(__name__)

# ── 프로젝트 루트 ──────────────────────────────────────────────────────────

# apps/api/src/worksheet_api/integrations/server_renderer.py → 프로젝트 루트 6단계 위
_PROJECT_ROOT = Path(__file__).parents[5]
_RENDER_DIR = _PROJECT_ROOT / "apps" / "render"

# ── 환경변수 ────────────────────────────────────────────────────────────────

_NODE_BIN: str = os.environ.get("NODE_BIN", "node")

# JITI_BIN: workspace TypeScript source 런타임 실행기.
# apps/render/node_modules/.bin/jiti 가 기본 (pnpm install 후 자동 생성).
_JITI_BIN: str = os.environ.get(
    "JITI_BIN",
    str(_RENDER_DIR / "node_modules" / ".bin" / "jiti"),
)

# SERVER_RENDERER_PATH: bin.ts 경로 (jiti로 실행할 TypeScript 파일).
_SERVER_RENDERER_PATH: str = os.environ.get(
    "SERVER_RENDERER_PATH",
    str(_RENDER_DIR / "src" / "bin.ts"),
)

# LEGACY_ANNOTATION_RENDERER: "true" 이면 annotation_html.py fallback 사용.
# Stage F2 초기 안전망. 충분한 production 검증 후 제거.
_LEGACY_RENDERER: bool = os.environ.get("LEGACY_ANNOTATION_RENDERER", "false").lower() == "true"

# subprocess 타임아웃 (초)
_SUBPROCESS_TIMEOUT: int = int(os.environ.get("SERVER_RENDERER_TIMEOUT", "30"))


def _passage_to_dict(passage: Passage) -> dict[str, object]:
    """Passage → CLI JSON 형식 dict 변환.

    CLI bin.ts 의 PassageForRender 타입과 일치:
      { body_text: str, paragraphs: str[] }
    """
    return {
        "body_text": passage.body_text,
        "paragraphs": list(passage.paragraphs) if passage.paragraphs else [],
    }


def _annotation_to_dict(ann: SyntaxAnnotation) -> dict[str, object]:
    """SyntaxAnnotation → CLI JSON 형식 dict 변환.

    CLI types.ts 의 SyntaxAnnotation 타입과 일치.
    None 값은 포함하지 않아 불필요한 null 전달 방지.
    """
    d: dict[str, object] = {
        "kind": ann.kind.value,
        "span": {
            "span_format": ann.span.span_format,
            "start": ann.span.start,
            "end": ann.span.end,
        },
    }
    if ann.color_index is not None:
        d["color_index"] = ann.color_index
    if ann.text is not None:
        d["text"] = ann.text
    if ann.bracket_style is not None:
        d["bracket_style"] = ann.bracket_style
    if ann.category is not None:
        d["category"] = ann.category.value if hasattr(ann.category, "value") else ann.category
    if ann.annotation_id is not None:
        d["annotation_id"] = str(ann.annotation_id)
    return d


def render_annotations_html_via_node(
    passage: Passage,
    annotations: list[SyntaxAnnotation],
) -> str:
    """server-side Tiptap (Node.js subprocess) 로 annotation HTML을 렌더링한다.

    환경변수 ``LEGACY_ANNOTATION_RENDERER=true`` 설정 시 기존
    ``annotation_html.py.render_annotations_to_html()`` 로 fallback한다.

    Args:
        passage: 대상 Passage (body_text + paragraphs).
        annotations: 적용할 SyntaxAnnotation 목록.

    Returns:
        str: Tiptap View DOM innerHTML — ProseMirror mark span + Decoration.widget 포함.
             fallback 시 annotation_html.py 의 Markup 문자열 (str로 변환).

    Raises:
        RuntimeError: Node.js 프로세스 실패 또는 타임아웃 시.
                      (fallback 없는 경우에만 발생)
    """
    if _LEGACY_RENDERER:
        logger.info(
            "server_renderer: LEGACY_ANNOTATION_RENDERER=true — annotation_html.py fallback"
        )
        return _render_via_legacy(passage, annotations)

    return _render_via_node(passage, annotations)


def _get_jiti_cmd() -> list[str]:
    """jiti 실행 커맨드 목록 반환.

    jiti 바이너리가 존재하면 직접 사용, 없으면 `node --import jiti/register` 방식으로
    fallback. 마지막 대안으로 `node` 직접 실행 (dist/bin.js 필요).
    """
    jiti_path = Path(_JITI_BIN)
    if jiti_path.exists():
        return [str(jiti_path)]

    # jiti 글로벌 설치 여부 확인
    import shutil

    global_jiti = shutil.which("jiti")
    if global_jiti:
        return [global_jiti]

    logger.warning(
        "server_renderer: jiti not found at %s — "
        "falling back to node (requires dist/bin.js build)",
        _JITI_BIN,
    )
    return [_NODE_BIN]


def _get_script_path(cmd: list[str]) -> str:
    """실행 커맨드에 따라 올바른 스크립트 경로 반환.

    jiti 사용 시: bin.ts (TypeScript 직접 실행).
    node 사용 시: dist/bin.js (빌드된 파일).
    """
    if cmd[0] != _NODE_BIN:
        # jiti path — bin.ts 직접 실행
        return _SERVER_RENDERER_PATH

    # node 직접 실행 — dist/bin.js 필요 (tsc build)
    dist_bin = str(_RENDER_DIR / "dist" / "bin.js")
    if not Path(dist_bin).exists():
        raise RuntimeError(
            f"server_renderer: Neither jiti nor dist/bin.js found. "
            f"Run `pnpm --filter @english-worksheet-tool/render build:cli` "
            f"or install jiti in {_RENDER_DIR}."
        )
    return dist_bin


def _render_via_node(passage: Passage, annotations: list[SyntaxAnnotation]) -> str:
    """Node.js CLI subprocess 호출 후 HTML 반환.

    실패 시 RuntimeError 발생 (호출자가 처리).
    """
    cmd = _get_jiti_cmd()
    script_path = _get_script_path(cmd)

    payload = json.dumps(
        {
            "passage": _passage_to_dict(passage),
            "annotations": [_annotation_to_dict(a) for a in annotations],
        },
        ensure_ascii=False,
    )

    try:
        result = subprocess.run(
            [*cmd, script_path],
            input=payload,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
            check=False,
            cwd=str(_RENDER_DIR),  # jiti 가 node_modules 를 올바르게 resolve 하도록
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"server_renderer: Node.js subprocess timed out after {_SUBPROCESS_TIMEOUT}s"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"server_renderer: executable not found: {cmd[0]!r}. "
            "Set NODE_BIN or JITI_BIN env var to correct path."
        ) from exc

    if result.returncode != 0:
        stderr_msg = result.stderr.strip()
        raise RuntimeError(
            f"server_renderer: Node.js exited with code {result.returncode}. "
            f"stderr: {stderr_msg}"
        )

    html = result.stdout
    if not html:
        logger.warning(
            "server_renderer: Node.js returned empty HTML — "
            "passage_id=%s, annotations=%d",
            passage.id,
            len(annotations),
        )

    logger.debug(
        "server_renderer: rendered %d chars, annotations=%d, passage_id=%s",
        len(html),
        len(annotations),
        passage.id,
    )
    return html


def _render_via_legacy(passage: Passage, annotations: list[SyntaxAnnotation]) -> str:
    """annotation_html.py legacy fallback.

    Stage F2 (2026-05-15) — LEGACY_ANNOTATION_RENDERER=true 일 때만 호출.
    Phase 2.5 종료 + production 검증 후 폐기 예정.
    """
    from template_renderer.annotation_html import render_annotations_to_html  # noqa: PLC0415

    return str(render_annotations_to_html(passage, annotations))
