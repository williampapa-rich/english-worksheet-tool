/**
 * annotationSerializer 단위 테스트 (vitest)
 *
 * DoD (P1-1): 5건 이상 — 각 kind 1건 + 다중 mark 1건.
 *
 * 테스트 전략:
 *   - Tiptap editor 인스턴스 없이 직접 JSONContent 를 구성해 테스트한다.
 *     (JSDOM 없는 vitest 환경에서 editor.getJSON() 대신 mock doc JSON 사용)
 *   - docToAnnotations → annotationsToMarks round-trip 검증으로
 *     ADR-0004 §"직렬화 → DB → 역직렬화 round-trip 검증" 항목을 만족한다.
 *
 * 커버리지:
 *   1. highlight 단일 mark (AnnotationKind.HIGHLIGHT)
 *   2. underline 단일 mark (AnnotationKind.UNDERLINE)
 *   3. top_label 단일 mark + text 속성 (AnnotationKind.TOP_LABEL)
 *   4. bracket 단일 mark + bracketStyle (AnnotationKind.BRACKET)
 *   5. arrow 단일 mark + arrowTargetSpan (AnnotationKind.ARROW)
 *   6. inline_note 단일 mark + text (AnnotationKind.INLINE_NOTE)
 *   7. bottom_label 단일 mark + text (AnnotationKind.BOTTOM_LABEL)
 *   8. 다중 mark — highlight + top_label 동일 span 겹침
 *   9. StarterKit mark (bold) 는 무시됨 검증
 *  10. round-trip: docToAnnotations → annotationsToMarks → 동일 span 복원
 */

import type { JSONContent } from "@tiptap/core";
import { describe, expect, it } from "vitest";
import { ANNOTATION_KIND } from "../extensions/annotationKind";
import {
  type MarkAttrs,
  type SerializedAnnotation,
  annotationsToMarks,
  charOffsetToPmPos,
  docToAnnotations,
  pmPosToCharOffset,
} from "./annotationSerializer";

/**
 * 배열 첫 번째 요소를 안전하게 가져오는 테스트 헬퍼.
 * biome 의 noNonNullAssertion 규칙을 우회하기 위해 명시적 undefined 체크 사용.
 */
function first<T>(arr: T[]): T {
  const item = arr[0];
  if (item === undefined) {
    throw new Error("Expected non-empty array but got empty array");
  }
  return item;
}

// ---------------------------------------------------------------------------
// 헬퍼 — mock doc JSON 생성
// ---------------------------------------------------------------------------

/**
 * 단일 단락, 단일 텍스트 노드 mock doc.
 * "Hello world" 같은 단순 문장.
 */
function makeDoc(
  paragraphs: Array<{
    segments: Array<{
      text: string;
      marks?: Array<{ type: string; attrs?: Record<string, unknown> }>;
    }>;
  }>
): JSONContent {
  return {
    type: "doc",
    content: paragraphs.map((para) => ({
      type: "paragraph",
      content: para.segments.map((seg) => ({
        type: "text",
        text: seg.text,
        ...(seg.marks ? { marks: seg.marks } : {}),
      })),
    })),
  };
}

// ---------------------------------------------------------------------------
// 테스트 케이스
// ---------------------------------------------------------------------------

describe("docToAnnotations", () => {
  // 테스트 1: highlight 단일 mark
  it("highlight mark 를 HIGHLIGHT kind 로 직렬화한다", () => {
    // "The " (4자) + "student" (7자, highlight) + " passed" (7자)
    const doc = makeDoc([
      {
        segments: [
          { text: "The " },
          {
            text: "student",
            marks: [{ type: "highlight", attrs: { color: "#fef08a" } }],
          },
          { text: " passed" },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);

    expect(annotations).toHaveLength(1);
    const ann: SerializedAnnotation = first(annotations);
    expect(ann.kind).toBe(ANNOTATION_KIND.HIGHLIGHT);
    expect(ann.span.span_format).toBe("character_offset_v1");
    expect(ann.span.data.start).toBe(4); // "The " = 4 chars
    expect(ann.span.data.end).toBe(11); // 4 + 7 = 11
  });

  // 테스트 2: underline 단일 mark
  it("underline mark 를 UNDERLINE kind 로 직렬화한다", () => {
    // "Scientists " (11자) + "have" (4자, underline)
    const doc = makeDoc([
      {
        segments: [
          { text: "Scientists " },
          { text: "have", marks: [{ type: "underline" }] },
          { text: " discovered" },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);

    expect(annotations).toHaveLength(1);
    const ann: SerializedAnnotation = first(annotations);
    expect(ann.kind).toBe(ANNOTATION_KIND.UNDERLINE);
    expect(ann.span.data.start).toBe(11);
    expect(ann.span.data.end).toBe(15); // 11 + 4
  });

  // 테스트 3: top_label mark + text 속성
  it("topLabel mark 를 TOP_LABEL kind 로 직렬화하고 text 속성을 보존한다", () => {
    // "The " (4자) + "student who studied hard" (24자, topLabel "S")
    const doc = makeDoc([
      {
        segments: [
          { text: "The " },
          {
            text: "student who studied hard",
            marks: [
              {
                type: "topLabel",
                attrs: { text: "S", colorIndex: 1 },
              },
            ],
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);

    expect(annotations).toHaveLength(1);
    const ann: SerializedAnnotation = first(annotations);
    expect(ann.kind).toBe(ANNOTATION_KIND.TOP_LABEL);
    expect(ann.text).toBe("S");
    expect(ann.color_index).toBe(1);
    expect(ann.span.data.start).toBe(4);
    expect(ann.span.data.end).toBe(28); // 4 + 24
  });

  // 테스트 4: bracket mark + bracketStyle
  it("bracket mark 를 BRACKET kind 로 직렬화하고 bracketStyle 을 보존한다", () => {
    // "who studied hard" (16자, bracket)
    const doc = makeDoc([
      {
        segments: [
          {
            text: "who studied hard",
            marks: [
              {
                type: "bracket",
                attrs: { bracketStyle: "()", colorIndex: 3 },
              },
            ],
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);

    expect(annotations).toHaveLength(1);
    const ann: SerializedAnnotation = first(annotations);
    expect(ann.kind).toBe(ANNOTATION_KIND.BRACKET);
    expect(ann.bracket_style).toBe("()");
    expect(ann.color_index).toBe(3);
    expect(ann.span.data.start).toBe(0);
    expect(ann.span.data.end).toBe(16);
  });

  // 테스트 5: arrow mark + arrowTargetSpan
  it("arrow mark 를 ARROW kind 로 직렬화하고 arrow_target_span 을 보존한다", () => {
    // "it" (2자, arrow pointing to 10-12)
    const doc = makeDoc([
      {
        segments: [
          {
            text: "it",
            marks: [
              {
                type: "arrow",
                attrs: { arrowTargetStart: 10, arrowTargetEnd: 16 },
              },
            ],
          },
          { text: " refers to " },
          { text: "oxygen" },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);

    expect(annotations).toHaveLength(1);
    const ann: SerializedAnnotation = first(annotations);
    expect(ann.kind).toBe(ANNOTATION_KIND.ARROW);
    expect(ann.span.data.start).toBe(0);
    expect(ann.span.data.end).toBe(2);
    expect(ann.arrow_target_span).not.toBeNull();
    expect(ann.arrow_target_span?.span_format).toBe("character_offset_v1");
    expect(ann.arrow_target_span?.data.start).toBe(10);
    expect(ann.arrow_target_span?.data.end).toBe(16);
  });

  // 테스트 6: inline_note mark + text
  it("inlineNote mark 를 INLINE_NOTE kind 로 직렬화하고 text 를 보존한다", () => {
    const doc = makeDoc([
      {
        segments: [
          { text: "The " },
          {
            text: "promote",
            marks: [
              {
                type: "inlineNote",
                attrs: { text: "=foster, encourage" },
              },
            ],
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);

    expect(annotations).toHaveLength(1);
    const ann: SerializedAnnotation = first(annotations);
    expect(ann.kind).toBe(ANNOTATION_KIND.INLINE_NOTE);
    expect(ann.text).toBe("=foster, encourage");
    expect(ann.span.data.start).toBe(4);
    expect(ann.span.data.end).toBe(11); // 4 + 7
  });

  // 테스트 7: bottom_label mark + text
  it("bottomLabel mark 를 BOTTOM_LABEL kind 로 직렬화하고 text 를 보존한다", () => {
    const doc = makeDoc([
      {
        segments: [
          {
            text: "Scientists",
            marks: [
              {
                type: "bottomLabel",
                attrs: { text: "S" },
              },
            ],
          },
          { text: " discovered" },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);

    expect(annotations).toHaveLength(1);
    const ann: SerializedAnnotation = first(annotations);
    expect(ann.kind).toBe(ANNOTATION_KIND.BOTTOM_LABEL);
    expect(ann.text).toBe("S");
    expect(ann.span.data.start).toBe(0);
    expect(ann.span.data.end).toBe(10);
  });

  // 테스트 8: 다중 mark — highlight + topLabel 동일 span 겹침
  it("동일 span 에 여러 mark 가 있으면 각각을 독립 annotation 으로 직렬화한다", () => {
    // "The student" 에서 "student" (4~11) 에 highlight + topLabel 동시 적용
    const doc = makeDoc([
      {
        segments: [
          { text: "The " },
          {
            text: "student",
            marks: [
              { type: "highlight", attrs: { color: "#fef08a" } },
              { type: "topLabel", attrs: { text: "S" } },
            ],
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);

    expect(annotations).toHaveLength(2);
    const kinds = annotations.map((a) => a.kind).sort();
    expect(kinds).toContain(ANNOTATION_KIND.HIGHLIGHT);
    expect(kinds).toContain(ANNOTATION_KIND.TOP_LABEL);
    // 두 annotation 의 span 이 동일해야 함
    for (const ann of annotations) {
      expect(ann.span.data.start).toBe(4);
      expect(ann.span.data.end).toBe(11);
    }
  });

  // 테스트 9: StarterKit mark (bold) 는 무시됨
  it("알 수 없는 mark (bold 등) 는 annotation 으로 변환하지 않는다", () => {
    const doc = makeDoc([
      {
        segments: [
          {
            text: "important",
            marks: [{ type: "bold" }],
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    expect(annotations).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// annotationsToMarks 테스트
// ---------------------------------------------------------------------------

describe("annotationsToMarks", () => {
  // 테스트 10: round-trip — docToAnnotations → annotationsToMarks
  it("round-trip: 직렬화 후 역직렬화하면 동일 span (pmPos) 를 복원한다", () => {
    // "The " (4) + "student" (7, highlight)
    const doc = makeDoc([
      {
        segments: [
          { text: "The " },
          { text: "student", marks: [{ type: "highlight", attrs: { color: "#ff0" } }] },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    const marks = annotationsToMarks(annotations);

    expect(marks).toHaveLength(1);
    const m: MarkAttrs = first(marks);
    // charOffset 4 → pmPos charOffsetToPmPos(4) = 6
    // charOffset 11 → pmPos charOffsetToPmPos(11) = 13
    expect(m.from).toBe(charOffsetToPmPos(4));
    expect(m.to).toBe(charOffsetToPmPos(11));
    expect(m.kind).toBe(ANNOTATION_KIND.HIGHLIGHT);
    expect(m.markName).toBe("highlight");
  });

  it("top_label annotation 을 mark 정보로 역직렬화한다", () => {
    const annotations = [
      {
        kind: ANNOTATION_KIND.TOP_LABEL,
        span: {
          span_format: "character_offset_v1" as const,
          data: { start: 0, end: 8 },
        },
        text: "S",
        color_index: 2,
      },
    ];

    const marks = annotationsToMarks(annotations);

    expect(marks).toHaveLength(1);
    const m: MarkAttrs = first(marks);
    expect(m.markName).toBe("topLabel");
    expect(m.attrs.text).toBe("S");
    expect(m.attrs.colorIndex).toBe(2);
    expect(m.from).toBe(charOffsetToPmPos(0));
    expect(m.to).toBe(charOffsetToPmPos(8));
  });
});

// ---------------------------------------------------------------------------
// 변환 헬퍼 테스트
// ---------------------------------------------------------------------------

describe("charOffsetToPmPos / pmPosToCharOffset", () => {
  it("charOffsetToPmPos 는 charOffset 에 2 를 더한 값을 반환한다", () => {
    expect(charOffsetToPmPos(0)).toBe(2);
    expect(charOffsetToPmPos(4)).toBe(6);
    expect(charOffsetToPmPos(11)).toBe(13);
  });

  it("pmPosToCharOffset 는 charOffsetToPmPos 의 역함수다", () => {
    for (const offset of [0, 1, 5, 10, 100]) {
      expect(pmPosToCharOffset(charOffsetToPmPos(offset))).toBe(offset);
    }
  });
});
