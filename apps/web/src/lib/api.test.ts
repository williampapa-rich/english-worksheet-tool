/**
 * api.test.ts — docToAnnotations ↔ annotationsToMarks round-trip 단위 테스트 (P1-6)
 *
 * 검증: 7종 annotation kind 각 1건 + top_label+bracket 동일 annotationId 공유 1건.
 * mock fetch / mock editor 없음 — 직렬화 함수만 호출.
 *
 * 검증 필드: kind / span / color_index / text / bracket_style /
 *            arrow_target_span / category / annotation_id
 *
 * 주의: annotationsToMarks 의 pmPos 계산은 charOffsetToPmPos(offset) = offset + 2
 * (단일 단락 가정). docToAnnotations 는 ProseMirror JSON 에서 charOffset 을 누적해
 * 직접 추출하므로 round-trip 에서 span 값은 원본 그대로 복원된다.
 */

import { annotationsToMarks, docToAnnotations } from "@english-worksheet-tool/editor";
import type { SerializedAnnotation } from "@english-worksheet-tool/editor";
import { describe, expect, it } from "vitest";

// ---------------------------------------------------------------------------
// 헬퍼 — ProseMirror JSON 문서 생성
// ---------------------------------------------------------------------------

/**
 * makeParagraphDoc — 단일 단락 ProseMirror JSON 생성.
 *
 * content 배열 안의 item 은 { text, marks } 형식.
 * marks 는 Tiptap mark JSON: { type: string, attrs: Record<string, unknown> }
 */
function makeParagraphDoc(
  items: Array<{
    text: string;
    marks?: Array<{ type: string; attrs?: Record<string, unknown> }>;
  }>
) {
  return {
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: items.map((item) => ({
          type: "text",
          text: item.text,
          ...(item.marks ? { marks: item.marks } : {}),
        })),
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// 1. highlight round-trip
// ---------------------------------------------------------------------------

describe("highlight round-trip", () => {
  it("kind / span / color_index / category / annotation_id 보존", () => {
    const doc = makeParagraphDoc([
      {
        text: "hello",
        marks: [
          {
            type: "highlight",
            attrs: {
              color: "#fef08a",
              colorIndex: 1,
              category: "note",
              annotationId: "hl-uuid-001",
            },
          },
        ],
      },
      { text: " world" },
    ]);

    const annotations = docToAnnotations(doc);
    expect(annotations).toHaveLength(1);
    const ann = annotations[0] as SerializedAnnotation;

    expect(ann.kind).toBe("highlight");
    expect(ann.span.start).toBe(0);
    expect(ann.span.end).toBe(5);
    expect(ann.color_index).toBe(1);
    expect(ann.category).toBe("note");
    expect(ann.annotation_id).toBe("hl-uuid-001");

    // annotationsToMarks 역직렬화
    const marks = annotationsToMarks(annotations);
    expect(marks).toHaveLength(1);
    const m = marks[0];
    expect(m?.kind).toBe("highlight");
    expect(m?.from).toBe(1); // charOffset 0 → pmPos 1 (P1-10a fix: +1 not +2)
    expect(m?.to).toBe(6); // charOffset 5 → pmPos 6
    expect(m?.attrs.colorIndex).toBe(1);
    expect(m?.attrs.annotationId).toBe("hl-uuid-001");
  });
});

// ---------------------------------------------------------------------------
// 2. underline round-trip
// ---------------------------------------------------------------------------

describe("underline round-trip", () => {
  it("kind / span / color_index / category / annotation_id 보존", () => {
    const doc = makeParagraphDoc([
      { text: "foo" },
      {
        text: "bar",
        marks: [
          {
            type: "underline",
            attrs: { colorIndex: 3, category: "note", annotationId: "ul-uuid-002" },
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    expect(annotations).toHaveLength(1);
    const ann = annotations[0] as SerializedAnnotation;

    expect(ann.kind).toBe("underline");
    expect(ann.span.start).toBe(3); // "foo" 이후
    expect(ann.span.end).toBe(6);
    expect(ann.color_index).toBe(3);
    expect(ann.category).toBe("note");
    expect(ann.annotation_id).toBe("ul-uuid-002");

    const marks = annotationsToMarks(annotations);
    const m = marks[0];
    expect(m?.from).toBe(4); // charOffset 3 → pmPos 4 (P1-10a fix: +1 not +2)
    expect(m?.to).toBe(7); // charOffset 6 → pmPos 7
  });
});

// ---------------------------------------------------------------------------
// 3. top_label round-trip
// ---------------------------------------------------------------------------

describe("top_label round-trip", () => {
  it("kind / span / text / color_index / category / annotation_id 보존", () => {
    const doc = makeParagraphDoc([
      {
        text: "subject",
        marks: [
          {
            type: "topLabel",
            attrs: {
              text: "S",
              colorIndex: 2,
              category: "phrase",
              annotationId: "tl-uuid-003",
            },
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    expect(annotations).toHaveLength(1);
    const ann = annotations[0] as SerializedAnnotation;

    expect(ann.kind).toBe("top_label");
    expect(ann.text).toBe("S");
    expect(ann.span.start).toBe(0);
    expect(ann.span.end).toBe(7);
    expect(ann.color_index).toBe(2);
    expect(ann.category).toBe("phrase");
    expect(ann.annotation_id).toBe("tl-uuid-003");

    const marks = annotationsToMarks(annotations);
    const m = marks[0];
    expect(m?.attrs.text).toBe("S");
    expect(m?.attrs.annotationId).toBe("tl-uuid-003");
  });
});

// ---------------------------------------------------------------------------
// 4. bottom_label round-trip
// ---------------------------------------------------------------------------

describe("bottom_label round-trip", () => {
  it("kind / span / text / category / annotation_id 보존", () => {
    const doc = makeParagraphDoc([
      {
        text: "runs",
        marks: [
          {
            type: "bottomLabel",
            attrs: {
              text: "V",
              colorIndex: 4,
              category: "sentence_role",
              annotationId: "bl-uuid-004",
            },
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    const ann = annotations[0] as SerializedAnnotation;

    expect(ann.kind).toBe("bottom_label");
    expect(ann.text).toBe("V");
    expect(ann.category).toBe("sentence_role");
    expect(ann.annotation_id).toBe("bl-uuid-004");

    const marks = annotationsToMarks(annotations);
    expect(marks[0]?.attrs.text).toBe("V");
  });
});

// ---------------------------------------------------------------------------
// 5. bracket round-trip
// ---------------------------------------------------------------------------

describe("bracket round-trip", () => {
  it("kind / span / bracket_style / color_index / annotation_id 보존", () => {
    const doc = makeParagraphDoc([
      {
        text: "clause",
        marks: [
          {
            type: "bracket",
            attrs: {
              bracketStyle: "[]",
              colorIndex: 5,
              category: "note",
              annotationId: "br-uuid-005",
            },
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    const ann = annotations[0] as SerializedAnnotation;

    expect(ann.kind).toBe("bracket");
    expect(ann.bracket_style).toBe("[]");
    expect(ann.color_index).toBe(5);
    expect(ann.annotation_id).toBe("br-uuid-005");

    const marks = annotationsToMarks(annotations);
    expect(marks[0]?.attrs.bracketStyle).toBe("[]");
  });
});

// ---------------------------------------------------------------------------
// 6. inline_note round-trip
// ---------------------------------------------------------------------------

describe("inline_note round-trip", () => {
  it("kind / span / text / category / annotation_id 보존", () => {
    const doc = makeParagraphDoc([
      {
        text: "foster",
        marks: [
          {
            type: "inlineNote",
            attrs: {
              text: "=promote",
              colorIndex: 6,
              category: "note",
              annotationId: "in-uuid-006",
            },
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    const ann = annotations[0] as SerializedAnnotation;

    expect(ann.kind).toBe("inline_note");
    expect(ann.text).toBe("=promote");
    expect(ann.category).toBe("note");
    expect(ann.annotation_id).toBe("in-uuid-006");

    const marks = annotationsToMarks(annotations);
    expect(marks[0]?.attrs.text).toBe("=promote");
  });
});

// ---------------------------------------------------------------------------
// 7. arrow round-trip
// ---------------------------------------------------------------------------

describe("arrow round-trip", () => {
  it("kind / span / arrow_target_span / color_index / annotation_id 보존", () => {
    const doc = makeParagraphDoc([
      {
        text: "it",
        marks: [
          {
            type: "arrow",
            attrs: {
              arrowTargetStart: 10,
              arrowTargetEnd: 18,
              colorIndex: 7,
              category: "note",
              annotationId: "ar-uuid-007",
            },
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    const ann = annotations[0] as SerializedAnnotation;

    expect(ann.kind).toBe("arrow");
    expect(ann.arrow_target_span?.start).toBe(10);
    expect(ann.arrow_target_span?.end).toBe(18);
    expect(ann.color_index).toBe(7);
    expect(ann.annotation_id).toBe("ar-uuid-007");

    const marks = annotationsToMarks(annotations);
    const m = marks[0];
    expect(m?.attrs.arrowTargetStart).toBe(10);
    expect(m?.attrs.arrowTargetEnd).toBe(18);
  });
});

// ---------------------------------------------------------------------------
// 8. top_label + bracket 동일 annotationId 공유 round-trip
// ---------------------------------------------------------------------------

describe("top_label + bracket 동일 annotationId 공유 round-trip", () => {
  it("같은 annotationId 의 두 mark 가 각각 직렬화되고 round-trip 에서 annotation_id 보존", () => {
    const sharedId = "shared-uuid-008";
    const doc = makeParagraphDoc([
      {
        text: "the big dog",
        marks: [
          {
            type: "topLabel",
            attrs: {
              text: "NP",
              colorIndex: 2,
              category: "phrase",
              annotationId: sharedId,
            },
          },
          {
            type: "bracket",
            attrs: {
              bracketStyle: "()",
              colorIndex: 2,
              category: "phrase",
              annotationId: sharedId,
            },
          },
        ],
      },
    ]);

    const annotations = docToAnnotations(doc);
    // top_label + bracket → 2개 annotation (docToAnnotations 는 mark 단위로 직렬화)
    expect(annotations).toHaveLength(2);

    const topLabel = annotations.find((a) => a.kind === "top_label") as
      | SerializedAnnotation
      | undefined;
    const bracket = annotations.find((a) => a.kind === "bracket") as
      | SerializedAnnotation
      | undefined;

    expect(topLabel).toBeDefined();
    expect(bracket).toBeDefined();

    // annotation_id 동일
    expect(topLabel?.annotation_id).toBe(sharedId);
    expect(bracket?.annotation_id).toBe(sharedId);

    // span 동일
    expect(topLabel?.span.start).toBe(0);
    expect(topLabel?.span.end).toBe(11);
    expect(bracket?.span.start).toBe(0);
    expect(bracket?.span.end).toBe(11);

    // text / bracket_style
    expect(topLabel?.text).toBe("NP");
    expect(bracket?.bracket_style).toBe("()");

    // round-trip — annotationsToMarks
    const marks = annotationsToMarks(annotations);
    expect(marks).toHaveLength(2);

    const mTopLabel = marks.find((m) => m.kind === "top_label");
    const mBracket = marks.find((m) => m.kind === "bracket");

    expect(mTopLabel?.attrs.annotationId).toBe(sharedId);
    expect(mBracket?.attrs.annotationId).toBe(sharedId);
    expect(mTopLabel?.attrs.text).toBe("NP");
    expect(mBracket?.attrs.bracketStyle).toBe("()");
  });
});
