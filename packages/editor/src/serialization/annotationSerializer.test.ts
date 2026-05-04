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
import { describe, expect, it, vi } from "vitest";
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
    expect(ann.span.start).toBe(4); // "The " = 4 chars
    expect(ann.span.end).toBe(11); // 4 + 7 = 11
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
    expect(ann.span.start).toBe(11);
    expect(ann.span.end).toBe(15); // 11 + 4
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
    expect(ann.span.start).toBe(4);
    expect(ann.span.end).toBe(28); // 4 + 24
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
    expect(ann.span.start).toBe(0);
    expect(ann.span.end).toBe(16);
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
    expect(ann.span.start).toBe(0);
    expect(ann.span.end).toBe(2);
    expect(ann.arrow_target_span).not.toBeNull();
    expect(ann.arrow_target_span?.span_format).toBe("character_offset_v1");
    expect(ann.arrow_target_span?.start).toBe(10);
    expect(ann.arrow_target_span?.end).toBe(16);
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
    expect(ann.span.start).toBe(4);
    expect(ann.span.end).toBe(11); // 4 + 7
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
    expect(ann.span.start).toBe(0);
    expect(ann.span.end).toBe(10);
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
      expect(ann.span.start).toBe(4);
      expect(ann.span.end).toBe(11);
    }
  });

  // 테스트 9a: arrow mark — arrowTargetStart/End 중 하나가 null 이면 drop + console.warn
  it("arrow mark 에 arrowTargetStart/End 가 없으면 annotation 을 drop 하고 console.warn 을 호출한다", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    // arrowTargetEnd 만 null
    const doc = makeDoc([
      {
        segments: [
          {
            text: "it",
            marks: [
              {
                type: "arrow",
                attrs: { arrowTargetStart: 10, arrowTargetEnd: null },
              },
            ],
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);

    expect(annotations).toHaveLength(0);
    expect(warnSpy).toHaveBeenCalledOnce();
    expect(warnSpy.mock.calls[0]?.[0]).toContain("ARROW");

    warnSpy.mockRestore();
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
          start: 0,
          end: 8,
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
// annotationId 직렬화 / 역직렬화 테스트 (P1-2b)
// ---------------------------------------------------------------------------

describe("annotationId — docToAnnotations + annotationsToMarks", () => {
  it("mark attrs 에 annotationId 가 있으면 annotation_id 로 직렬화한다", () => {
    const id = "test-uuid-1234";
    const doc = makeDoc([
      {
        segments: [
          {
            text: "student",
            marks: [
              {
                type: "topLabel",
                attrs: { text: "S", colorIndex: 1, annotationId: id },
              },
            ],
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    expect(annotations).toHaveLength(1);
    expect(first(annotations).annotation_id).toBe(id);
  });

  it("mark attrs 에 annotationId 가 없으면 annotation_id 는 undefined 다", () => {
    const doc = makeDoc([
      {
        segments: [
          {
            text: "student",
            marks: [{ type: "highlight", attrs: { color: "#fef08a" } }],
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    expect(annotations).toHaveLength(1);
    expect(first(annotations).annotation_id).toBeUndefined();
  });

  it("annotationsToMarks 에서 annotation_id → annotationId attr 로 역직렬화한다", () => {
    const id = "round-trip-uuid";
    const annotations = [
      {
        kind: ANNOTATION_KIND.TOP_LABEL,
        span: { span_format: "character_offset_v1" as const, start: 0, end: 5 },
        text: "V",
        annotation_id: id,
      },
    ];

    const marks = annotationsToMarks(annotations);
    expect(marks).toHaveLength(1);
    expect(first(marks).attrs.annotationId).toBe(id);
  });

  it("annotation_id round-trip: docToAnnotations → annotationsToMarks → attrs.annotationId 보존", () => {
    const id = "full-round-trip-uuid";
    const doc = makeDoc([
      {
        segments: [
          {
            text: "passed",
            marks: [
              {
                type: "bracket",
                attrs: { bracketStyle: "()", colorIndex: 2, annotationId: id },
              },
            ],
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    const marks = annotationsToMarks(annotations);
    expect(first(marks).attrs.annotationId).toBe(id);
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

  // 신규 8건 — 다중 단락 변환

  // 신규 1: 단일 단락 charOffsetToPmPos +2 회귀 (paragraphLengths 1개)
  it("[다중단락] paragraphLengths 가 1개이면 단일 단락 로직 (+2) 과 동일하다", () => {
    // 단락 1개: "Hello" (5자)
    const lens = [5];
    expect(charOffsetToPmPos(0, lens)).toBe(2);
    expect(charOffsetToPmPos(3, lens)).toBe(5);
    expect(charOffsetToPmPos(5, lens)).toBe(7);
  });

  // 신규 2: 다중 단락 — 첫 단락 안 charOffsetToPmPos 정확
  it("[다중단락] 첫 단락 안 charOffset 을 pmPos 로 정확히 변환한다", () => {
    // 단락0: "Hello" (5자), 단락1: "World" (5자)
    // body_text = "Hello\nWorld"
    // 단락0 첫 글자 charOffset=0 → pmPos=2, 끝 charOffset=5 → pmPos=7
    const lens = [5, 5];
    expect(charOffsetToPmPos(0, lens)).toBe(2); // 첫 글자
    expect(charOffsetToPmPos(4, lens)).toBe(6); // 'o' (index 4)
    expect(charOffsetToPmPos(5, lens)).toBe(7); // 단락 끝 위치 (len 포함)
  });

  // 신규 3: 다중 단락 — 두 번째 단락 안 charOffsetToPmPos 정확
  it("[다중단락] 두 번째 단락 안 charOffset 을 pmPos 로 정확히 변환한다", () => {
    // 단락0: "Hello" (5자), 단락1: "World" (5자)
    // body_text = "Hello\nWorld"
    // 단락1 첫 글자 charOffset = 5+1 = 6
    // pmPos 공식: 2 + 5 + 2*1 + 0 = 9
    const lens = [5, 5];
    expect(charOffsetToPmPos(6, lens)).toBe(9); // 두 번째 단락 첫 글자
    expect(charOffsetToPmPos(10, lens)).toBe(13); // 두 번째 단락 끝 (6+4)
    expect(charOffsetToPmPos(11, lens)).toBe(14); // 두 번째 단락 끝+1 (마지막 pmPos)
  });

  // 신규 4: 다중 단락 pmPosToCharOffset — 첫 단락 정확
  it("[다중단락] 첫 단락 pmPos 를 charOffset 으로 정확히 변환한다", () => {
    // 단락0: "Hello" (5자), 단락1: "World" (5자)
    const lens = [5, 5];
    expect(pmPosToCharOffset(2, lens)).toBe(0); // 첫 글자
    expect(pmPosToCharOffset(6, lens)).toBe(4); // index 4
    expect(pmPosToCharOffset(7, lens)).toBe(5); // 단락0 끝
  });

  // 신규 5: 다중 단락 pmPosToCharOffset — 두 번째 단락 정확
  it("[다중단락] 두 번째 단락 pmPos 를 charOffset 으로 정확히 변환한다", () => {
    // 단락0: "Hello" (5자), 단락1: "World" (5자)
    // 단락1 첫 글자 pmPos = 2 + 5 + 2 = 9
    const lens = [5, 5];
    expect(pmPosToCharOffset(9, lens)).toBe(6); // 두 번째 단락 첫 글자 charOffset
    expect(pmPosToCharOffset(13, lens)).toBe(10); // 마지막 글자 charOffset
  });

  // 신규 6: round-trip charOffset → pmPos → charOffset (다중 단락)
  it("[다중단락] round-trip: charOffset → pmPos → charOffset 이 일치한다", () => {
    // 단락0: "ABCDE" (5자), 단락1: "FGHIJ" (5자), 단락2: "KL" (2자)
    // body_text = "ABCDE\nFGHIJ\nKL"
    const lens = [5, 5, 2];
    const offsets = [0, 2, 5, 6, 9, 11, 12, 13];
    for (const off of offsets) {
      expect(pmPosToCharOffset(charOffsetToPmPos(off, lens), lens)).toBe(off);
    }
  });
});

// ---------------------------------------------------------------------------
// 다중 단락 collectMarksFromDoc + annotationsToMarks 통합 테스트
// ---------------------------------------------------------------------------

describe("다중 단락 — collectMarksFromDoc + annotationsToMarks", () => {
  // 신규 7: collectMarksFromDoc 다중 단락 — 두 번째 단락의 mark charStart 가 body_text 인덱스와 일치
  it("두 번째 단락의 mark charStart/charEnd 가 body_text (join \\n) 인덱스와 일치한다", () => {
    // 단락0: "Hello " (6자) + "world" (5자, highlight) = 11자
    // 단락1: "Scientists " (11자) + "have" (4자, underline)
    // body_text = "Hello world\nScientists have"
    // "Scientists " 의 charOffset = 11 (단락0) + 1 (\n) = 12
    // "have" charStart = 12 + 11 = 23, charEnd = 23 + 4 = 27
    const doc = makeDoc([
      {
        segments: [
          { text: "Hello " },
          { text: "world", marks: [{ type: "highlight", attrs: { color: "#ff0" } }] },
        ],
      },
      {
        segments: [{ text: "Scientists " }, { text: "have", marks: [{ type: "underline" }] }],
      },
    ]);

    const annotations = docToAnnotations(doc);
    expect(annotations).toHaveLength(2);

    const highlight = annotations.find((a) => a.kind === "highlight");
    const underline = annotations.find((a) => a.kind === "underline");

    // 첫 단락: "Hello " = 6, "world" charStart=6, charEnd=11
    expect(highlight?.span.start).toBe(6);
    expect(highlight?.span.end).toBe(11);

    // 두 번째 단락: "Scientists " = 11자 → "have" charStart = 12 + 11 = 23
    expect(underline?.span.start).toBe(23);
    expect(underline?.span.end).toBe(27);
  });

  // 신규 8: annotationsToMarks 다중 단락 — paragraphLengths 전달 시 from/to 정확
  it("paragraphLengths 전달 시 두 번째 단락의 from/to 가 정확한 pmPos 를 반환한다", () => {
    // 단락0: "Hello world" (11자), 단락1: "Scientists have" (15자)
    // "have" charStart=23, charEnd=27
    // paragraphLengths = [11, 15]
    // pmPos(23) = 2 + 11 + 2*1 + (23-12) = 2 + 11 + 2 + 11 = 26
    // pmPos(27) = 2 + 11 + 2*1 + (27-12) = 2 + 11 + 2 + 15 = 30
    const paragraphLengths = [11, 15];
    const annotations: import("./annotationSerializer").SerializedAnnotation[] = [
      {
        kind: "underline" as import("../extensions/annotationKind").AnnotationKind,
        span: { span_format: "character_offset_v1", start: 23, end: 27 },
      },
    ];

    const marks = annotationsToMarks(annotations, paragraphLengths);
    expect(marks).toHaveLength(1);
    const m = first(marks);
    expect(m.from).toBe(26);
    expect(m.to).toBe(30);
  });
});
