"""hwpx_renderer — HWPX 출력 패키지.

공개 API:
    render_passage_with_annotations(passage, annotations) -> bytes
        P1-8 공식 entrypoint. passage + annotation 목록 → HWPX bytes.
        P1-8a: highlight / underline / inline_note 지원.
        P1-8b/c: top_label / bottom_label / bracket / arrow (예정).
"""

from hwpx_renderer.render import render_passage_with_annotations

__all__ = ["render_passage_with_annotations"]
