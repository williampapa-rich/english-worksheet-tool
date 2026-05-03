/**
 * HighlightMark — 구문분석 하이라이트 extension (AnnotationKind.HIGHLIGHT)
 *
 * CLAUDE.md §3.6 원칙에 따라 @tiptap/extension-highlight 를 베이스로,
 * multicolor 옵션을 활성화한 가벼운 래퍼만 제공한다.
 *
 * 선택 이유 (대안 검토):
 *   - @tiptap/extension-highlight: 공식 Tiptap highlight, multicolor 지원 내장 → 채택
 *   - 직접 Mark 구현: ProseMirror 저수준 작업 필요, Tiptap 우선 원칙 위반 → 기각
 *
 * multicolor: true 로 설정해야 나중에 색상별로 의미 구분(주어 = 노랑, 동사 = 초록 등)이 가능.
 *
 * NOTE: AnnotationKind.HIGHLIGHT 의 TypeScript 미러 값 = "highlight"
 * (shared/schemas/annotation.py AnnotationKind.HIGHLIGHT = "highlight")
 * Python schema 변경 시 ANNOTATION_KIND 상수 파일도 동기화 필요.
 */
import Highlight from "@tiptap/extension-highlight";

export const HighlightMark = Highlight.configure({
  multicolor: true,
});

export { Highlight as HighlightBase };
