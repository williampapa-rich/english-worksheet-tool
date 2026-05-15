/**
 * ServerTiptapPreview — Stage F1 PoC: browser-side Tiptap (generateHTML 경로) 미리보기
 *
 * `/preview/server-tiptap?scenario=C1|C2|C3|zero-waste` 로 접근.
 *
 * 목적: Playwright E2E spec (F1-e) 에서 browser-side 에디터 ↔
 *       generateHTML 기반 서버 렌더 HTML 의 wrap 위치를 비교.
 *
 * 주의: PoC 전용 라우트. 프로덕션 라우트 아님.
 * 이 페이지는 apps/render/src/serverRenderer 의 jsdom 없는 "generateHTML" 경로를
 * 브라우저에서 동작하는 버전으로 복제한다.
 * (apps/render → apps/web 직접 import 금지 — Node.js env 코드 포함 위험)
 */

import { generateHTML } from "@tiptap/html";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  BottomLabelMark,
  BracketMark,
  HighlightMark,
  InlineNoteMark,
  TopLabelMark,
  UnderlineMark,
} from "@english-worksheet-tool/editor";

import "@templates/_passage_body.css";

// ─── 인라인 타입 (apps/render/src/types.ts 미러, Node dep 없음) ──────────────

type AnnotationKind =
  | "highlight"
  | "underline"
  | "top_label"
  | "bottom_label"
  | "bracket"
  | "inline_note"
  | "arrow";

type BracketStyle = "()" | "{}" | "[]" | "⌜⌟" | "<>";

interface CharacterOffsetV1Span {
  span_format: "character_offset_v1";
  start: number;
  end: number;
}

interface SyntaxAnnotation {
  kind: AnnotationKind;
  span: CharacterOffsetV1Span;
  color_index?: number | null;
  text?: string | null;
  bracket_style?: BracketStyle | null;
  category?: string | null;
  annotation_id?: string | null;
}

interface PassageForRender {
  body_text: string;
  paragraphs: string[];
}

// ─── annotationsToTiptapDoc 인라인 (apps/render/src/annotationsToTiptapDoc.ts) ─

const KIND_TO_MARK_NAME: Record<string, string> = {
  highlight: "highlight",
  underline: "underline",
  top_label: "topLabel",
  bottom_label: "bottomLabel",
  bracket: "bracket",
  inline_note: "inlineNote",
  arrow: "arrow",
};

function charOffsetToLocation(
  charOffset: number,
  paragraphLengths: number[]
): { paraIdx: number; localOffset: number } {
  if (paragraphLengths.length <= 1) {
    return { paraIdx: 0, localOffset: charOffset };
  }
  let acc = 0;
  for (let i = 0; i < paragraphLengths.length; i++) {
    const len = paragraphLengths[i] ?? 0;
    const paraStartChar = acc + i;
    const paraEndChar = paraStartChar + len;
    if (charOffset <= paraEndChar) {
      const localOffset = charOffset - paraStartChar;
      if (localOffset < 0) return { paraIdx: i + 1, localOffset: 0 };
      return { paraIdx: i, localOffset };
    }
    acc += len;
  }
  const lastLen = paragraphLengths[paragraphLengths.length - 1] ?? 0;
  return { paraIdx: paragraphLengths.length - 1, localOffset: lastLen };
}

function buildMarkMap(
  annotations: SyntaxAnnotation[],
  paragraphLengths: number[]
): Map<number, Map<number, { type: string; attrs: Record<string, unknown> }[]>> {
  const markMap = new Map<
    number,
    Map<number, { type: string; attrs: Record<string, unknown> }[]>
  >();
  for (let i = 0; i < paragraphLengths.length; i++) markMap.set(i, new Map());

  for (const ann of annotations) {
    if (ann.kind === "arrow") continue;
    const markName = KIND_TO_MARK_NAME[ann.kind];
    if (!markName) continue;
    const startLoc = charOffsetToLocation(ann.span.start, paragraphLengths);
    const endLoc = charOffsetToLocation(ann.span.end, paragraphLengths);
    const attrs: Record<string, unknown> = {};
    if (ann.annotation_id) attrs.annotationId = ann.annotation_id;
    if (ann.color_index != null) attrs.colorIndex = ann.color_index;
    if (ann.category != null) attrs.category = ann.category;
    if (ann.kind === "highlight") attrs.color = null;
    if (ann.kind === "top_label" || ann.kind === "bottom_label" || ann.kind === "inline_note")
      attrs.text = ann.text ?? null;
    if (ann.kind === "bracket") attrs.bracketStyle = (ann.bracket_style as BracketStyle) ?? "()";
    const mark = { type: markName, attrs };

    for (
      let pi = startLoc.paraIdx;
      pi <= Math.min(endLoc.paraIdx, paragraphLengths.length - 1);
      pi++
    ) {
      const paraLen = paragraphLengths[pi] ?? 0;
      const localStart = pi === startLoc.paraIdx ? startLoc.localOffset : 0;
      const localEnd = pi === endLoc.paraIdx ? endLoc.localOffset : paraLen;
      const paraMap = markMap.get(pi);
      if (!paraMap) continue;
      for (let c = localStart; c < localEnd; c++) {
        const existing = paraMap.get(c) ?? [];
        paraMap.set(c, [...existing, mark]);
      }
    }
  }
  return markMap;
}

function buildParagraphContent(
  paragraphText: string,
  charMarkMap: Map<number, { type: string; attrs: Record<string, unknown> }[]>
) {
  if (!paragraphText) return [];
  const nodes: {
    type: "text";
    text: string;
    marks?: { type: string; attrs: Record<string, unknown> }[];
  }[] = [];
  let cursor = 0;
  while (cursor < paragraphText.length) {
    const currentMarks = charMarkMap.get(cursor) ?? [];
    const currentKey = JSON.stringify(currentMarks);
    let end = cursor + 1;
    while (end < paragraphText.length && JSON.stringify(charMarkMap.get(end) ?? []) === currentKey)
      end++;
    const node: (typeof nodes)[0] = { type: "text", text: paragraphText.slice(cursor, end) };
    if (currentMarks.length > 0) node.marks = currentMarks;
    nodes.push(node);
    cursor = end;
  }
  return nodes;
}

function annotationsToTiptapDoc(passage: PassageForRender, annotations: SyntaxAnnotation[]) {
  const paragraphs = passage.paragraphs.length > 0 ? passage.paragraphs : [passage.body_text];
  const paragraphLengths = paragraphs.map((p) => p.length);
  const markMap = buildMarkMap(annotations, paragraphLengths);
  return {
    type: "doc",
    content: paragraphs.map((paraText, i) => {
      const paraMarkMap = markMap.get(i) ?? new Map();
      const content = buildParagraphContent(paraText, paraMarkMap);
      return { type: "paragraph", content: content.length > 0 ? content : undefined };
    }),
  };
}

// ─── Fixture 데이터 ───────────────────────────────────────────────────────────

const C1_PASSAGE: PassageForRender = {
  body_text:
    "These supermarkets and grocery stores attempt to prevent waste by eliminating plastic packages altogether.",
  paragraphs: [
    "These supermarkets and grocery stores attempt to prevent waste by eliminating plastic packages altogether.",
  ],
};

const C1_ANNOTATIONS: SyntaxAnnotation[] = [
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

const C2_PASSAGE: PassageForRender = {
  body_text:
    "both seller and buyer work together (to minimize the negative impact on the environment.)",
  paragraphs: [
    "both seller and buyer work together (to minimize the negative impact on the environment.)",
  ],
};

const C2_ANNOTATIONS: SyntaxAnnotation[] = [
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

const C3_PASSAGE: PassageForRender = {
  body_text: "Currently, there are more than {70 zero-waste stores in Seoul}.",
  paragraphs: ["Currently, there are more than {70 zero-waste stores in Seoul}."],
};

const C3_ANNOTATIONS: SyntaxAnnotation[] = [
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

// ─── Zero Waste 전체 passage (7 paragraphs) — F2-e spec 용 ─────────────────

const ZERO_WASTE_PASSAGE: PassageForRender = {
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

const ZERO_WASTE_ANNOTATIONS: SyntaxAnnotation[] = [];

type Scenario = "C1" | "C2" | "C3" | "zero-waste";

function getScenarioData(scenario: string): {
  passage: PassageForRender;
  annotations: SyntaxAnnotation[];
} {
  if (scenario === "C2") return { passage: C2_PASSAGE, annotations: C2_ANNOTATIONS };
  if (scenario === "C3") return { passage: C3_PASSAGE, annotations: C3_ANNOTATIONS };
  if (scenario === "zero-waste")
    return { passage: ZERO_WASTE_PASSAGE, annotations: ZERO_WASTE_ANNOTATIONS };
  return { passage: C1_PASSAGE, annotations: C1_ANNOTATIONS };
}

// ─── 에디터 extensions ────────────────────────────────────────────────────────

const EXTENSIONS = [
  StarterKit,
  HighlightMark,
  UnderlineMark,
  TopLabelMark,
  BottomLabelMark,
  BracketMark,
  InlineNoteMark,
];

// ─── 컴포넌트 ─────────────────────────────────────────────────────────────────

export function ServerTiptapPreview() {
  const [searchParams] = useSearchParams();
  const scenario = (searchParams.get("scenario") ?? "C1") as Scenario;
  const [html, setHtml] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const { passage, annotations } = getScenarioData(scenario);
      const doc = annotationsToTiptapDoc(passage, annotations);
      // biome-ignore lint/suspicious/noExplicitAny: Tiptap typing
      const rendered = generateHTML(doc as any, EXTENSIONS as any);
      setHtml(rendered);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [scenario]);

  if (error) {
    return (
      <div className="p-4 text-red-600">
        <p data-error="true">Server Tiptap PoC 오류: {error}</p>
      </div>
    );
  }

  return (
    <div
      data-server-tiptap-preview="true"
      data-scenario={scenario}
      className="q-content passage-body"
      style={{ width: "626px", margin: "0 auto", padding: "0" }}
      // biome-ignore lint/security/noDangerouslySetInnerHtml: PoC 내부 fixture 데이터
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
