/**
 * Zero Waste 검수 fixture — Stage F1 핵심 검증 시나리오
 *
 * 와이프 v0.2 검수에서 발견된 wrap 어긋남 케이스 재현용.
 * - worksheet: 74c1a9e0-f973-495c-b1d6-09c33ba194a1
 * - passage: 104309e6-b77c-4945-a7a6-95d0ca8f9e50
 *
 * 사전 가이드 §2.1 참조.
 *
 * DB 없이 서버 사이드 PoC 가 동작하도록 인라인 fixture 제공.
 * 실제 DB 값과 diff 가 있으면 DB 값 우선 (본 파일은 PoC 전용).
 */

import type { PassageForRender, SyntaxAnnotation } from "../types.js";

/**
 * C1 시나리오 — 단일 paragraph
 *
 * "These supermarkets and grocery stores attempt to prevent waste by eliminating
 * plastic packages altogether."
 *
 * 목표: `eliminating` 다음 줄바꿈 (에디터와 동일)
 * 현 PDF 결과: `eliminating plastic` 같은 줄 (annotation_html.py 출력)
 */
export const C1_PASSAGE: PassageForRender = {
  body_text:
    "These supermarkets and grocery stores attempt to prevent waste by eliminating plastic packages altogether.",
  paragraphs: [
    "These supermarkets and grocery stores attempt to prevent waste by eliminating plastic packages altogether.",
  ],
};

export const C1_ANNOTATIONS: SyntaxAnnotation[] = [
  // 실제 DB annotation 반영: "prevent waste" 에 top_label "목적어구"
  {
    kind: "top_label",
    span: {
      span_format: "character_offset_v1",
      start: C1_PASSAGE.body_text.indexOf(
        "prevent waste by eliminating plastic packages altogether"
      ),
      end:
        C1_PASSAGE.body_text.indexOf("prevent waste by eliminating plastic packages altogether") +
        "prevent waste by eliminating plastic packages altogether".length,
    },
    text: "목적어구",
    annotation_id: "c1-ann-1",
  },
];

/**
 * C2 시나리오 — 라벨 + bracket
 *
 * "both seller and buyer work together (to minimize the negative impact on the environment.)"
 *
 * 목표: `together` / `(to minimize ... on the` / `environment.)` 3 줄 (에디터와 동일)
 */
export const C2_PASSAGE: PassageForRender = {
  body_text:
    "both seller and buyer work together (to minimize the negative impact on the environment.)",
  paragraphs: [
    "both seller and buyer work together (to minimize the negative impact on the environment.)",
  ],
};

export const C2_ANNOTATIONS: SyntaxAnnotation[] = [
  // top_label on "seller and buyer"
  {
    kind: "top_label",
    span: {
      span_format: "character_offset_v1",
      start: C2_PASSAGE.body_text.indexOf("seller and buyer"),
      end: C2_PASSAGE.body_text.indexOf("seller and buyer") + "seller and buyer".length,
    },
    text: "주어",
    annotation_id: "c2-ann-1",
  },
  // bracket "()" on "to minimize the negative impact on the environment."
  {
    kind: "bracket",
    span: {
      span_format: "character_offset_v1",
      start: C2_PASSAGE.body_text.indexOf("to minimize"),
      end:
        C2_PASSAGE.body_text.indexOf("to minimize") +
        "to minimize the negative impact on the environment.".length,
    },
    bracket_style: "()",
    annotation_id: "c2-ann-2",
  },
];

/**
 * C3 시나리오 — curly bracket
 *
 * "Currently, there are more than {70 zero-waste stores in Seoul}."
 *
 * 목표: 동일 (C3 는 이미 OK)
 */
export const C3_PASSAGE: PassageForRender = {
  body_text: "Currently, there are more than {70 zero-waste stores in Seoul}.",
  paragraphs: ["Currently, there are more than {70 zero-waste stores in Seoul}."],
};

export const C3_ANNOTATIONS: SyntaxAnnotation[] = [
  // bracket "{}" on "70 zero-waste stores in Seoul"
  {
    kind: "bracket",
    span: {
      span_format: "character_offset_v1",
      start: C3_PASSAGE.body_text.indexOf("70 zero-waste stores in Seoul"),
      end:
        C3_PASSAGE.body_text.indexOf("70 zero-waste stores in Seoul") +
        "70 zero-waste stores in Seoul".length,
    },
    bracket_style: "{}",
    annotation_id: "c3-ann-1",
  },
];

/**
 * Zero Waste 실제 passage (7 paragraphs, annotation 11개) 근사 fixture.
 *
 * C1/C2/C3 를 포함하는 전체 passage — Playwright 검증 시 사용.
 * 정확한 annotation span 은 DB 에서 로드하거나 seed_phase1_fixtures.py 참고.
 */
export const ZERO_WASTE_PASSAGE: PassageForRender = {
  body_text:
    "Zero-waste stores have emerged as a response to growing concerns about plastic pollution.\n" +
    "These supermarkets and grocery stores attempt to prevent waste by eliminating plastic packages altogether.\n" +
    "Customers bring their own containers or bags and fill them with the exact quantities they need.\n" +
    "In this way, both seller and buyer work together (to minimize the negative impact on the environment.)\n" +
    "Currently, there are more than {70 zero-waste stores in Seoul}.\n" +
    "This number continues to grow as more consumers become aware of environmental issues.\n" +
    "The movement represents a significant shift in how people think about everyday shopping.",
  paragraphs: [
    "Zero-waste stores have emerged as a response to growing concerns about plastic pollution.",
    "These supermarkets and grocery stores attempt to prevent waste by eliminating plastic packages altogether.",
    "Customers bring their own containers or bags and fill them with the exact quantities they need.",
    "In this way, both seller and buyer work together (to minimize the negative impact on the environment.)",
    "Currently, there are more than {70 zero-waste stores in Seoul}.",
    "This number continues to grow as more consumers become aware of environmental issues.",
    "The movement represents a significant shift in how people think about everyday shopping.",
  ],
};

function findOffset(text: string, phrase: string): number {
  const idx = text.indexOf(phrase);
  if (idx === -1) throw new Error(`phrase not found: "${phrase}"`);
  return idx;
}

const ZW_BODY = ZERO_WASTE_PASSAGE.body_text;

export const ZERO_WASTE_ANNOTATIONS: SyntaxAnnotation[] = [
  // Paragraph 2: top_label "목적어구" on "prevent waste by eliminating plastic packages altogether"
  {
    kind: "top_label",
    span: {
      span_format: "character_offset_v1",
      start: findOffset(ZW_BODY, "prevent waste by eliminating plastic packages altogether"),
      end:
        findOffset(ZW_BODY, "prevent waste by eliminating plastic packages altogether") +
        "prevent waste by eliminating plastic packages altogether".length,
    },
    text: "목적어구",
    annotation_id: "zw-ann-1",
  },
  // Paragraph 4: top_label "주어" on "seller and buyer"
  {
    kind: "top_label",
    span: {
      span_format: "character_offset_v1",
      start: findOffset(ZW_BODY, "seller and buyer"),
      end: findOffset(ZW_BODY, "seller and buyer") + "seller and buyer".length,
    },
    text: "주어",
    annotation_id: "zw-ann-2",
  },
  // Paragraph 4: bracket "()" on "to minimize the negative impact on the environment."
  {
    kind: "bracket",
    span: {
      span_format: "character_offset_v1",
      start: findOffset(ZW_BODY, "to minimize"),
      end:
        findOffset(ZW_BODY, "to minimize") +
        "to minimize the negative impact on the environment.".length,
    },
    bracket_style: "()",
    annotation_id: "zw-ann-3",
  },
  // Paragraph 5: bracket "{}" on "70 zero-waste stores in Seoul"
  {
    kind: "bracket",
    span: {
      span_format: "character_offset_v1",
      start: findOffset(ZW_BODY, "70 zero-waste stores in Seoul"),
      end:
        findOffset(ZW_BODY, "70 zero-waste stores in Seoul") +
        "70 zero-waste stores in Seoul".length,
    },
    bracket_style: "{}",
    annotation_id: "zw-ann-4",
  },
  // highlight on "plastic packages altogether"
  {
    kind: "highlight",
    span: {
      span_format: "character_offset_v1",
      start: findOffset(ZW_BODY, "plastic packages altogether"),
      end:
        findOffset(ZW_BODY, "plastic packages altogether") + "plastic packages altogether".length,
    },
    color_index: 3,
    annotation_id: "zw-ann-5",
  },
];
