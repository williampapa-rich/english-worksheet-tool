/**
 * Stage F1 — Server-side Tiptap PoC: 공유 타입 정의
 *
 * Python shared/schemas/annotation.py 의 TypeScript 미러.
 * annotationSerializer.ts 의 SerializedAnnotation 과 동일 구조.
 */

export type AnnotationKind =
  | "highlight"
  | "underline"
  | "top_label"
  | "bottom_label"
  | "bracket"
  | "inline_note"
  | "arrow";

export type BracketStyle = "()" | "{}" | "[]" | "⌜⌟" | "<>";

export interface CharacterOffsetV1Span {
  span_format: "character_offset_v1";
  start: number;
  end: number;
}

export interface SyntaxAnnotation {
  kind: AnnotationKind;
  span: CharacterOffsetV1Span;
  color_index?: number | null;
  text?: string | null;
  bracket_style?: BracketStyle | null;
  arrow_target_span?: CharacterOffsetV1Span | null;
  category?: string | null;
  annotation_id?: string | null;
}

export interface PassageForRender {
  body_text: string;
  paragraphs: string[];
}

/**
 * Tiptap JSON doc format
 */
export interface TiptapTextMark {
  type: string;
  attrs?: Record<string, unknown>;
}

export interface TiptapTextNode {
  type: "text";
  text: string;
  marks?: TiptapTextMark[];
}

export interface TiptapParagraphNode {
  type: "paragraph";
  content?: TiptapTextNode[];
}

export interface TiptapDoc {
  type: "doc";
  content: TiptapParagraphNode[];
}

/**
 * F1-b 호환성 분석 결과
 */
export interface CompatibilityReport {
  jsdom: {
    boots: boolean;
    generateHTML_works: boolean;
    prosemirror_view_works: boolean;
    decoration_widget_works: boolean;
    unsupported_apis: string[];
    errors: string[];
  };
  linkedom: {
    boots: boolean;
    errors: string[];
  };
  recommended: "jsdom" | "linkedom" | "neither";
  notes: string;
}
