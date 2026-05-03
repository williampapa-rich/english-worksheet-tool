/**
 * AnnotationKind — Python AnnotationKind enum 의 TypeScript 미러.
 *
 * 단일 source of truth 는 shared/schemas/annotation.py 의 AnnotationKind.
 * 이 파일은 Python schema 에서 수동 동기화된 상수다.
 *
 * IMPORTANT: shared/schemas/annotation.py 의 AnnotationKind enum 이 변경되면
 * 이 파일도 반드시 동기화해야 한다.
 *
 * 미래 개선: openapi-typescript 또는 자동 생성 도구로 교체 예정.
 * PR 근거: Phase 1 진입 속도 우선 — 자동 생성 파이프라인 구축보다 수동 미러링이
 * 빠르다. 자동화는 P1-5 (API 통합) 단계에서 함께 처리할 예정.
 */

/**
 * Annotation 종류 (Python AnnotationKind StrEnum 미러).
 *
 * 값은 Python 쪽 StrEnum 값과 1:1 대응한다.
 * 직렬화/역직렬화 시 이 상수를 사용한다.
 */
export const ANNOTATION_KIND = {
  TOP_LABEL: "top_label",
  BOTTOM_LABEL: "bottom_label",
  HIGHLIGHT: "highlight",
  BRACKET: "bracket",
  ARROW: "arrow",
  INLINE_NOTE: "inline_note",
  UNDERLINE: "underline",
} as const;

export type AnnotationKind = (typeof ANNOTATION_KIND)[keyof typeof ANNOTATION_KIND];

/**
 * Tiptap mark name → AnnotationKind 매핑 테이블.
 *
 * Tiptap mark 의 name (예: "topLabel") 을 직렬화할 때 Python AnnotationKind
 * 값 (예: "top_label") 으로 변환하는 데 사용한다.
 */
export const MARK_NAME_TO_KIND: Record<string, AnnotationKind> = {
  topLabel: ANNOTATION_KIND.TOP_LABEL,
  bottomLabel: ANNOTATION_KIND.BOTTOM_LABEL,
  highlight: ANNOTATION_KIND.HIGHLIGHT,
  bracket: ANNOTATION_KIND.BRACKET,
  arrow: ANNOTATION_KIND.ARROW,
  inlineNote: ANNOTATION_KIND.INLINE_NOTE,
  underline: ANNOTATION_KIND.UNDERLINE,
};

/**
 * AnnotationKind → Tiptap mark name 역매핑 테이블.
 */
export const KIND_TO_MARK_NAME: Record<AnnotationKind, string> = {
  [ANNOTATION_KIND.TOP_LABEL]: "topLabel",
  [ANNOTATION_KIND.BOTTOM_LABEL]: "bottomLabel",
  [ANNOTATION_KIND.HIGHLIGHT]: "highlight",
  [ANNOTATION_KIND.BRACKET]: "bracket",
  [ANNOTATION_KIND.ARROW]: "arrow",
  [ANNOTATION_KIND.INLINE_NOTE]: "inlineNote",
  [ANNOTATION_KIND.UNDERLINE]: "underline",
};
