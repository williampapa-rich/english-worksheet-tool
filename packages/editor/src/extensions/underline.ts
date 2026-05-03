/**
 * UnderlineMark — 밑줄 extension (AnnotationKind.UNDERLINE)
 *
 * CLAUDE.md §3.6 원칙에 따라 @tiptap/extension-underline 을 그대로 사용한다.
 *
 * 선택 이유 (대안 검토):
 *   - @tiptap/extension-underline: 공식 Tiptap underline extension → 채택
 *   - StarterKit 의 내장 underline: StarterKit 에는 underline 미포함 — 별도 패키지 필요
 *   - 직접 Mark 구현: Tiptap 공식 extension 이 있으므로 기각 (§3.6)
 *
 * NOTE: AnnotationKind.UNDERLINE 의 TypeScript 미러 값 = "underline"
 * (shared/schemas/annotation.py AnnotationKind.UNDERLINE = "underline")
 * Python schema 변경 시 ANNOTATION_KIND 상수 파일도 동기화 필요.
 */
import Underline from "@tiptap/extension-underline";

export const UnderlineMark = Underline;

export { Underline as UnderlineBase };
