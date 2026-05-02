/**
 * HighlightMark — 구문분석 하이라이트 extension
 *
 * CLAUDE.md 3.6 원칙에 따라 ProseMirror 마크를 직접 구현하지 않는다.
 * @tiptap/extension-highlight 을 베이스로, multicolor 옵션을 활성화한
 * 가벼운 래퍼만 제공한다.
 *
 * 선택 이유 (대안 검토):
 *   - @tiptap/extension-highlight: 공식 Tiptap highlight, multicolor 지원 내장 → 채택
 *   - 직접 Mark 구현: ProseMirror 저수준 작업 필요, Tiptap 우선 원칙 위반 → 기각
 *
 * multicolor: true 로 설정해야 나중에 색상별로 의미 구분(주어 = 노랑, 동사 = 초록 등)이 가능.
 * Phase 1에서 color 속성을 SyntaxAnnotation.color 와 매핑할 예정.
 */
import Highlight from "@tiptap/extension-highlight";

export const HighlightMark = Highlight.configure({
  // 여러 색상을 동시에 지원 — Phase 1에서 구문론적 역할별 색상 구분에 사용
  multicolor: true,
});

export { Highlight as HighlightBase };
