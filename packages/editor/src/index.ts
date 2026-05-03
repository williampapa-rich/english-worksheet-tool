/**
 * @english-worksheet-tool/editor — public API
 *
 * Phase 1 P1-1: 7종 AnnotationKind 에 대응하는 Tiptap extension 스텁 + 직렬화 계약.
 * Sprint 0 #7 의 HighlightMark 를 골격에 통합.
 */

// AnnotationKind 상수 (Python schema 미러)
export {
  ANNOTATION_KIND,
  MARK_NAME_TO_KIND,
  KIND_TO_MARK_NAME,
} from "./extensions/annotationKind";
export type { AnnotationKind } from "./extensions/annotationKind";

// Extensions
export { HighlightMark, HighlightBase } from "./extensions/highlight";
export { UnderlineMark, UnderlineBase } from "./extensions/underline";
export { TopLabelMark } from "./extensions/topLabel";
export type { TopLabelOptions } from "./extensions/topLabel";
export { BottomLabelMark } from "./extensions/bottomLabel";
export type { BottomLabelOptions } from "./extensions/bottomLabel";
export { BracketMark } from "./extensions/bracket";
export type { BracketOptions, BracketStyle } from "./extensions/bracket";
export { InlineNoteMark } from "./extensions/inlineNote";
export type { InlineNoteOptions } from "./extensions/inlineNote";
export { ArrowMark } from "./extensions/arrow";
export type { ArrowOptions } from "./extensions/arrow";
export { WordSnapExtension } from "./extensions/wordSnap";

// Serialization (P1-1 PR 단위 b)
export {
  docToAnnotations,
  annotationsToMarks,
  charOffsetToPmPos,
  pmPosToCharOffset,
} from "./serialization/annotationSerializer";
export type {
  SerializedAnnotation,
  MarkAttrs,
  AnnotationSpanV1,
} from "./serialization/annotationSerializer";
