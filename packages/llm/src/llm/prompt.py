"""PromptSpec — docs/prompts/ 마크다운 + frontmatter 로딩 및 변수 바인딩.

CLAUDE.md §8.3: 프롬프트는 docs/prompts/ 에 마크다운으로 버전 관리.

파일 포맷:
  ---
  model_hint: claude-sonnet-4-...
  description: 영어 지문 텍스트 추출용 프롬프트
  version: 0
  ---
  프롬프트 본문. {{variable}} 형태로 변수 삽입.

변수 치환:
  단순 {{name}} 패턴 사용. Jinja2 같은 무거운 템플릿 엔진 금지
  (CLAUDE.md §3.6 — 단순 string replace 충분).

  치환되지 않은 {{variable}} 가 남아있으면 render() 가 ValueError raise.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

# docs/prompts/ 의 기본 위치 — 프로젝트 루트 기준
# 환경변수 PROMPTS_DIR 로 override 가능 (테스트 등)
_DEFAULT_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent.parent / "docs" / "prompts"

# {{variable_name}} 패턴 — 단순 string 치환
_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _get_prompts_dir() -> Path:
    """프롬프트 디렉토리 경로 반환.

    환경변수 ``PROMPTS_DIR`` 가 설정된 경우 그 경로를 사용. 테스트에서
    임시 디렉토리를 주입하기 위해 사용한다.
    """
    import os

    override = os.environ.get("PROMPTS_DIR")
    if override:
        return Path(override)
    return _DEFAULT_PROMPTS_DIR


class PromptFrontmatter(BaseModel):
    """docs/prompts/ 마크다운 파일의 YAML frontmatter 메타.

    Attributes:
        model_hint: 권장 모델 ID. 실제 사용 모델은 환경변수가 최종 결정 — hint 만.
        description: 프롬프트 목적 설명.
        version: 버전 번호 (파일명의 vN 과 일치 권고, 단 파일명이 source of truth).
    """

    model_config = ConfigDict(extra="allow")  # 미래 필드 허용

    model_hint: str | None = Field(default=None)
    description: str | None = Field(default=None)
    version: int | str | None = Field(default=None)


class PromptSpec(BaseModel):
    """프롬프트 템플릿 명세 + 변수 바인딩.

    ``render()`` 를 호출하면 ``docs/prompts/<template_id>.md`` 에서 본문을 로드하고
    ``variables`` 로 치환한 최종 프롬프트 문자열을 반환한다.

    사용 예:
        spec = PromptSpec(
            template_id="extract-text-v0",
            variables={"passage_text": "...", "num_questions": "5"},
        )
        prompt_str = spec.render()

    Attributes:
        template_id: docs/prompts/ 의 파일명 (확장자 .md 제외). 예: "extract-text-v0".
        variables: {{name}} 변수 치환 dict. 모든 변수가 치환되어야 render() 성공.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(
        ...,
        description="docs/prompts/ 의 파일명 (확장자 제외). 예: 'extract-text-v0'.",
    )
    variables: dict[str, str] = Field(
        default_factory=dict,
        description="본문의 {{name}} 변수 치환 dict.",
    )

    def render(self) -> str:
        """프롬프트 본문 로드 + 변수 치환 후 최종 문자열 반환.

        Returns:
            치환 완료된 프롬프트 문자열.

        Raises:
            FileNotFoundError: 템플릿 파일이 없을 때.
            ValueError: 치환되지 않은 {{variable}} 가 남아있을 때.
        """
        body = self._load_body()
        rendered = self._substitute(body)
        return rendered

    def load_frontmatter(self) -> PromptFrontmatter:
        """frontmatter 메타를 파싱해서 반환.

        Returns:
            PromptFrontmatter 인스턴스.

        Raises:
            FileNotFoundError: 템플릿 파일이 없을 때.
        """
        raw_front, _ = self._parse_file()
        if not raw_front:
            return PromptFrontmatter()
        try:
            data: Any = yaml.safe_load(raw_front)
        except yaml.YAMLError as exc:
            raise ValueError(f"'{self.template_id}.md' frontmatter YAML 파싱 실패: {exc}") from exc
        if not isinstance(data, dict):
            return PromptFrontmatter()
        return PromptFrontmatter.model_validate(data)

    # ── private helpers ──────────────────────────────────────────────────────

    def _load_body(self) -> str:
        """파일에서 본문(frontmatter 제외)만 로드."""
        _, body = self._parse_file()
        return body.strip()

    def _parse_file(self) -> tuple[str | None, str]:
        """마크다운 파일을 (frontmatter_raw, body) 로 분리.

        Returns:
            (frontmatter_str_or_None, body_str) 튜플.
        """
        path = _get_prompts_dir() / f"{self.template_id}.md"
        if not path.exists():
            raise FileNotFoundError(
                f"프롬프트 파일을 찾을 수 없습니다: {path}\n"
                f"docs/prompts/{self.template_id}.md 가 존재하는지 확인하세요."
            )
        content = path.read_text(encoding="utf-8")
        return _split_frontmatter(content)

    def _substitute(self, body: str) -> str:
        """본문의 {{variable}} 를 variables 로 치환.

        치환 후 남은 {{...}} 가 있으면 ValueError raise (미정의 변수).
        """
        result = body
        for key, value in self.variables.items():
            result = result.replace(f"{{{{{key}}}}}", value)

        # 치환되지 않은 변수 검출
        remaining = _VAR_PATTERN.findall(result)
        if remaining:
            raise ValueError(
                f"프롬프트 '{self.template_id}.md' 에 치환되지 않은 변수가 있습니다: "
                f"{remaining}. variables dict 에 해당 키를 추가하세요."
            )
        return result


def _split_frontmatter(content: str) -> tuple[str | None, str]:
    """마크다운 파일을 frontmatter 와 본문으로 분리.

    frontmatter 는 파일 첫 줄이 ``---`` 이고 두 번째 ``---`` 으로 닫히는 YAML 블록.
    frontmatter 가 없으면 (None, 전체 내용) 반환.

    Args:
        content: 파일 전체 텍스트.

    Returns:
        (frontmatter_raw_or_None, body) 튜플.
    """
    if not content.startswith("---"):
        return None, content

    # 두 번째 --- 을 찾아 분리
    rest = content[3:]  # 첫 --- 건너뜀
    # 줄바꿈 뒤에 --- 패턴 탐색
    match = re.search(r"\n---\s*\n", rest)
    if not match:
        # 닫히는 --- 없으면 frontmatter 없는 것으로 처리
        return None, content

    frontmatter_raw = rest[: match.start()]
    body = rest[match.end() :]
    return frontmatter_raw, body
