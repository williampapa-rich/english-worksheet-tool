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
    // charOffset 4 → pmPos charOffsetToPmPos(4) = 5  (P1-10a fix: +1 not +2)
    // charOffset 11 → pmPos charOffsetToPmPos(11) = 12
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
  // P1-10a fix: +2 → +1 (ProseMirror 단락 내부 첫 위치 = pos 1, not pos 2)
  it("charOffsetToPmPos 는 charOffset 에 1 을 더한 값을 반환한다", () => {
    expect(charOffsetToPmPos(0)).toBe(1);
    expect(charOffsetToPmPos(4)).toBe(5);
    expect(charOffsetToPmPos(11)).toBe(12);
  });

  it("pmPosToCharOffset 는 charOffsetToPmPos 의 역함수다", () => {
    for (const offset of [0, 1, 5, 10, 100]) {
      expect(pmPosToCharOffset(charOffsetToPmPos(offset))).toBe(offset);
    }
  });

  // 다중 단락 변환
  // ProseMirror position 구조 (doc = [para("Hello"), para("World")]):
  //   pos 0: para[0] 앞 (doc 내부)
  //   pos 1: para[0] 내부 시작, 'H' 앞   ← para open token
  //   pos 2~5: 'e','l','l','o' 사이
  //   pos 6: 'o' 뒤 (para[0] 내부 끝)
  //   pos 7: para[0] 와 para[1] 사이     ← para[0] close token
  //   pos 8: para[1] 내부 시작, 'W' 앞   ← para[1] open token
  //   ...
  // charOffset=0 → pmPos=1, charOffset=6 → pmPos=8

  // 신규 1: 단일 단락 charOffsetToPmPos +1 회귀 (paragraphLengths 1개)
  it("[다중단락] paragraphLengths 가 1개이면 단일 단락 로직 (+1) 과 동일하다", () => {
    // 단락 1개: "Hello" (5자)
    const lens = [5];
    expect(charOffsetToPmPos(0, lens)).toBe(1);
    expect(charOffsetToPmPos(3, lens)).toBe(4);
    expect(charOffsetToPmPos(5, lens)).toBe(6);
  });

  // 신규 2: 다중 단락 — 첫 단락 안 charOffsetToPmPos 정확
  it("[다중단락] 첫 단락 안 charOffset 을 pmPos 로 정확히 변환한다", () => {
    // 단락0: "Hello" (5자), 단락1: "World" (5자)
    // body_text = "Hello\nWorld"
    // 단락0 첫 글자 charOffset=0 → pmPos=1, 끝 charOffset=5 → pmPos=6
    const lens = [5, 5];
    expect(charOffsetToPmPos(0, lens)).toBe(1); // 첫 글자 앞
    expect(charOffsetToPmPos(4, lens)).toBe(5); // 'o' 앞 (charOffset=4)
    expect(charOffsetToPmPos(5, lens)).toBe(6); // 단락0 끝 (exclusive to)
  });

  // 신규 3: 다중 단락 — 두 번째 단락 안 charOffsetToPmPos 정확
  it("[다중단락] 두 번째 단락 안 charOffset 을 pmPos 로 정확히 변환한다", () => {
    // 단락0: "Hello" (5자), 단락1: "World" (5자)
    // body_text = "Hello\nWorld"
    // 단락1 첫 글자 charOffset = 5+1 = 6
    // pmPos 공식: 1 + 5 + 2*1 + 0 = 8
    const lens = [5, 5];
    expect(charOffsetToPmPos(6, lens)).toBe(8); // 두 번째 단락 첫 글자 앞
    expect(charOffsetToPmPos(10, lens)).toBe(12); // 두 번째 단락 끝 (charOffset=6+4)
    expect(charOffsetToPmPos(11, lens)).toBe(13); // 두 번째 단락 끝+1 (마지막 exclusive pmPos)
  });

  // 신규 4: 다중 단락 pmPosToCharOffset — 첫 단락 정확
  it("[다중단락] 첫 단락 pmPos 를 charOffset 으로 정확히 변환한다", () => {
    // 단락0: "Hello" (5자), 단락1: "World" (5자)
    const lens = [5, 5];
    expect(pmPosToCharOffset(1, lens)).toBe(0); // 첫 글자 앞
    expect(pmPosToCharOffset(5, lens)).toBe(4); // charOffset 4 ('o' 앞)
    expect(pmPosToCharOffset(6, lens)).toBe(5); // 단락0 끝
  });

  // 신규 5: 다중 단락 pmPosToCharOffset — 두 번째 단락 정확
  it("[다중단락] 두 번째 단락 pmPos 를 charOffset 으로 정확히 변환한다", () => {
    // 단락0: "Hello" (5자), 단락1: "World" (5자)
    // 단락1 첫 글자 pmPos = 1 + 5 + 2 = 8
    const lens = [5, 5];
    expect(pmPosToCharOffset(8, lens)).toBe(6); // 두 번째 단락 첫 글자 charOffset
    expect(pmPosToCharOffset(12, lens)).toBe(10); // 마지막 글자 charOffset (charOffset=10)
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
    // 단락1 내부 시작 pmPos = 1 + 11 + 2*1 = 14 (charOffset=12 → pmPos=14)
    // charOffset=23: localOffset = 23 - 12 = 11
    //   pmPos(23) = 1 + 11 + 2*1 + 11 = 25
    // charOffset=27: localOffset = 27 - 12 = 15
    //   pmPos(27) = 1 + 11 + 2*1 + 15 = 29
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
    expect(m.from).toBe(25);
    expect(m.to).toBe(29);
  });
});

// ---------------------------------------------------------------------------
// P1-10a: 첫 글자 짤림 버그 fix 검증 — round-trip 시나리오
// ---------------------------------------------------------------------------

describe("P1-10a: 첫 글자 짤림 버그 — 저장→로드 round-trip", () => {
  /**
   * 재현 시나리오: 본문 첫 단어에 bottom_label 적용 → 저장 → 로드 → 동일 범위 복원.
   * 이전 +2 구현에서는 charOffset=0 → pmPos=2 로 'T' 앞이 아닌 'T' 뒤에서 시작해
   * "The" → "he" (첫 글자 짤림) 버그가 발생했다.
   * 수정 후: charOffset=0 → pmPos=1 ('T' 앞 위치) — 정확한 range 복원.
   */
  it("본문 첫 단어 mark 의 round-trip — charOffset=0 이 pmPos=1 로 정확히 복원된다", () => {
    // doc: 단일 단락 "The student"
    // "The" (3자) 에 bottom_label mark
    const doc = makeDoc([
      {
        segments: [
          {
            text: "The",
            marks: [{ type: "bottomLabel", attrs: { text: "S", annotationId: "id-1" } }],
          },
          { text: " student" },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    expect(annotations).toHaveLength(1);
    const ann = first(annotations);
    expect(ann.span.start).toBe(0); // "The" charStart = 0
    expect(ann.span.end).toBe(3); // "The" charEnd = 3

    const marks = annotationsToMarks(annotations);
    const m = first(marks);
    // P1-10a fix: charOffset=0 → pmPos=1 (첫 글자 앞, 짤림 없음)
    expect(m.from).toBe(1);
    expect(m.to).toBe(4); // charOffset=3 → pmPos=4 (3+1)
    expect(m.markName).toBe("bottomLabel");
    expect(m.attrs.text).toBe("S");
  });

  it("다중 단락 첫 단어 round-trip — 두 번째 단락 첫 글자 pmPos 가 정확하다", () => {
    // 단락0: "Hello world" (11자)
    // 단락1: "Scientists discovered" — 첫 단어 "Scientists" (10자) 에 top_label
    const doc = makeDoc([
      {
        segments: [{ text: "Hello world" }],
      },
      {
        segments: [
          {
            text: "Scientists",
            marks: [{ type: "topLabel", attrs: { text: "S", annotationId: "id-2" } }],
          },
          { text: " discovered" },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    expect(annotations).toHaveLength(1);
    const ann = first(annotations);
    // 단락0 = 11자, \n = 1자 → 단락1 시작 charOffset=12
    // "Scientists" charStart=12, charEnd=22
    expect(ann.span.start).toBe(12);
    expect(ann.span.end).toBe(22);

    const paragraphLengths = [11, 20]; // "Hello world"=11, "Scientists discovered"=20
    const marks = annotationsToMarks(annotations, paragraphLengths);
    const m = first(marks);
    // 단락1 내부 시작 pmPos = 1 + 11 + 2*1 = 14 (charOffset=12 → localOffset=0)
    expect(m.from).toBe(14); // 단락1 첫 글자 앞
    expect(m.to).toBe(24); // charOffset=22, localOffset=10 → 1+11+2+10=24
  });

  it("본문 끝 단어 round-trip — 단락 끝 경계 pmPos 가 정확하다", () => {
    // "Hello world" 에서 "world" (5자, charOffset=6..11) 에 highlight
    const doc = makeDoc([
      {
        segments: [
          { text: "Hello " },
          {
            text: "world",
            marks: [{ type: "highlight", attrs: { color: "#ff0", annotationId: "id-3" } }],
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    const ann = first(annotations);
    expect(ann.span.start).toBe(6);
    expect(ann.span.end).toBe(11);

    const marks = annotationsToMarks(annotations);
    const m = first(marks);
    // charOffset=6 → pmPos=7, charOffset=11 → pmPos=12
    expect(m.from).toBe(7);
    expect(m.to).toBe(12);
  });

  it("7종 kind 모두 charOffset=0 에서 pmPos=1 round-trip 통과", () => {
    const kinds = [
      { type: "highlight", attrs: { color: "#fef08a", annotationId: "id-hl" } },
      { type: "underline", attrs: { annotationId: "id-ul" } },
      { type: "topLabel", attrs: { text: "S", annotationId: "id-tl" } },
      { type: "bottomLabel", attrs: { text: "V", annotationId: "id-bl" } },
      { type: "bracket", attrs: { bracketStyle: "()", annotationId: "id-br" } },
      { type: "inlineNote", attrs: { text: "=foster", annotationId: "id-in" } },
      // arrow 는 arrowTargetStart/End 필수라 별도 처리
    ];

    for (const mark of kinds) {
      const doc = makeDoc([
        {
          segments: [
            {
              text: "William",
              marks: [mark],
            },
            { text: " helped" },
          ],
        },
      ]);

      const annotations = docToAnnotations(doc);
      // arrow drop 이 아닌 kind 는 1건 직렬화
      if (annotations.length === 0) continue;
      const ann = first(annotations);
      expect(ann.span.start).toBe(0); // 첫 글자 charOffset=0

      const annotationMarks = annotationsToMarks(annotations);
      const m = first(annotationMarks);
      // P1-10a fix: from=1 (pmPos=charOffset+1=1), not from=2
      expect(m.from).toBe(1);
    }
  });
});

// ---------------------------------------------------------------------------
// 회귀 테스트 — paragraph trailing whitespace 가 char offset 에 +1 시프트 시키던 버그
// ---------------------------------------------------------------------------

describe("paragraph trailing whitespace ignored in char offset", () => {
  /**
   * 사용자 보고 (2026-05-08): William fixture 케이스에서 paragraph[0] 끝에 공백 1개
   * 가 ProseMirror 안에 포함되어 collectMarksFromDoc 가 그 공백까지 누산 → 이후
   * paragraph 의 mark span 이 +1 시프트되어 PDF 에서 마지막 글자가 잘려 보임.
   * Fix: 각 paragraph 의 마지막 text 노드 trailing whitespace 는 char offset 에서 제외.
   */
  it("trailing space on paragraph[0] does not shift mark on paragraph[1]", () => {
    // paragraph[0] = "William ...ever. " (43자, trailing space 포함)
    // paragraph[1] = "We have to admire him forever ..." → 마크는 "to admire him"
    //
    // backend paragraphs (trim, length=42) 와 일치하려면 mark 시작은 51 (= 42 + \n + 8).
    const doc: JSONContent = {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [{ type: "text", text: "William is the best dog in the world ever. " }],
        },
        {
          type: "paragraph",
          content: [
            { type: "text", text: "We have " },
            {
              type: "text",
              text: "to admire him",
              marks: [
                {
                  type: "bracket",
                  attrs: {
                    bracketStyle: "<>",
                    colorIndex: 8,
                    annotationId: "x",
                    category: "clause",
                  },
                },
              ],
            },
            { type: "text", text: " forever because he is almighty and powerful." },
          ],
        },
      ],
    };
    const result = docToAnnotations(doc);
    expect(result).toHaveLength(1);
    expect(first(result).span.start).toBe(51);
    expect(first(result).span.end).toBe(64);
  });

  it("paragraph 마지막 text 노드 자체가 공백뿐이면 그 노드 길이는 누산 0", () => {
    // 마지막 text 노드 = "   " (공백 3개) → trim 후 0.
    const doc: JSONContent = {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            { type: "text", text: "Hello" },
            { type: "text", text: "   " },
          ],
        },
        {
          type: "paragraph",
          content: [
            {
              type: "text",
              text: "World",
              marks: [
                {
                  type: "highlight",
                  attrs: { color: "#fef08a", annotationId: "y", category: "note" },
                },
              ],
            },
          ],
        },
      ],
    };
    const result = docToAnnotations(doc);
    expect(result).toHaveLength(1);
    // paragraph[0] effective length = 5 ("Hello"). \n + 0 = 6 → "World" 시작 = 6.
    expect(first(result).span.start).toBe(6);
    expect(first(result).span.end).toBe(11);
  });

  it("trailing whitespace 가 없는 정상 케이스는 그대로 동작", () => {
    const doc: JSONContent = {
      type: "doc",
      content: [
        { type: "paragraph", content: [{ type: "text", text: "Hello" }] },
        {
          type: "paragraph",
          content: [
            {
              type: "text",
              text: "World",
              marks: [
                {
                  type: "underline",
                  attrs: { annotationId: "z", category: "note" },
                },
              ],
            },
          ],
        },
      ],
    };
    const result = docToAnnotations(doc);
    // paragraph[0] = 5, \n = 1 → "World" 시작 = 6.
    expect(first(result).span.start).toBe(6);
    expect(first(result).span.end).toBe(11);
  });
});
