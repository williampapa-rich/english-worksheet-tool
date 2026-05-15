/**
 * annotationsToTiptapDoc — SyntaxAnnotation[] + Passage → Tiptap JSON doc
 *
 * Stage F1 core: Python 의 annotation_html.py 와 대칭이지만,
 * Tiptap 에디터가 실제로 생성하는 JSON doc 구조를 서버에서 복원한다.
 *
 * 접근 방식:
 *   - packages/editor/src/serialization/annotationSerializer.ts 의
 *     annotationsToMarks() 의 역방향 로직을 활용.
 *   - 각 paragraph 를 Tiptap paragraph 노드로, 각 annotation 을 mark 로 변환.
 *   - top_label / bottom_label / bracket 은 mark 로 표현 (widget 은 generateHTML 에 불포함).
 *
 * 핵심 주의 (ADR-0018 §Stage F1, 사전 가이드 §1.2):
 *   Decoration.widget 은 generateHTML 에 포함되지 않는다.
 *   본 모듈은 mark 기반 HTML 출력 (generateHTML 경로) 의 정합성 검증용.
 *   widget 의 HTML 표현 (라벨 텍스트 / 괄호 글자) 은 별도 후처리로 주입.
 */

import type {
  BracketStyle,
  PassageForRender,
  SyntaxAnnotation,
  TiptapDoc,
  TiptapParagraphNode,
  TiptapTextMark,
  TiptapTextNode,
} from "./types.js";

// Tiptap mark name → AnnotationKind 매핑 (annotationKind.ts 미러)
const KIND_TO_MARK_NAME: Record<string, string> = {
  highlight: "highlight",
  underline: "underline",
  top_label: "topLabel",
  bottom_label: "bottomLabel",
  bracket: "bracket",
  inline_note: "inlineNote",
  arrow: "arrow",
};

/**
 * character offset (body_text 기준) → paragraph index + local offset 변환.
 *
 * annotationSerializer.ts 의 charOffsetToPmPos 와 동일 로직이지만
 * ProseMirror position 이 아닌 (paragraphIdx, localOffset) 반환.
 */
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
    const paraStartChar = acc + i; // 앞 단락 글자 수 + 단락 사이 \n 수
    const paraEndChar = paraStartChar + len;

    if (charOffset <= paraEndChar) {
      const localOffset = charOffset - paraStartChar;
      if (localOffset < 0) {
        // \n 경계 — 다음 단락 시작
        return { paraIdx: i + 1, localOffset: 0 };
      }
      return { paraIdx: i, localOffset };
    }
    acc += len;
  }

  // 범위 밖 → 마지막 단락 끝
  const lastLen = paragraphLengths[paragraphLengths.length - 1] ?? 0;
  return {
    paraIdx: paragraphLengths.length - 1,
    localOffset: lastLen,
  };
}

/**
 * 각 paragraph 의 각 character 에 적용되는 marks 를 계산.
 *
 * 반환: paragraphIdx → localOffset → Mark[] 배열
 */
function buildMarkMap(
  annotations: SyntaxAnnotation[],
  paragraphLengths: number[]
): Map<number, Map<number, TiptapTextMark[]>> {
  // paraIdx → localOffset → marks[]
  const markMap = new Map<number, Map<number, TiptapTextMark[]>>();

  for (let i = 0; i < paragraphLengths.length; i++) {
    markMap.set(i, new Map());
  }

  for (const ann of annotations) {
    if (ann.kind === "arrow") continue; // skip (ADR-0014 D4)

    const markName = KIND_TO_MARK_NAME[ann.kind];
    if (!markName) continue;

    const startLoc = charOffsetToLocation(ann.span.start, paragraphLengths);
    const endLoc = charOffsetToLocation(ann.span.end, paragraphLengths);

    // mark attrs 구성
    const attrs: Record<string, unknown> = {};
    if (ann.annotation_id) attrs.annotationId = ann.annotation_id;
    if (ann.color_index != null) attrs.colorIndex = ann.color_index;
    if (ann.category != null) attrs.category = ann.category;

    // kind-specific attrs
    if (ann.kind === "highlight") {
      // @tiptap/extension-highlight 는 "color" attr 사용
      attrs.color = null; // multicolor=true 시 null 허용
    }
    if (ann.kind === "top_label" || ann.kind === "bottom_label" || ann.kind === "inline_note") {
      attrs.text = ann.text ?? null;
    }
    if (ann.kind === "bracket") {
      attrs.bracketStyle = (ann.bracket_style as BracketStyle) ?? "()";
    }

    const mark: TiptapTextMark = { type: markName, attrs };

    // span 이 여러 paragraph 에 걸칠 수 있음
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

/**
 * 연속된 동일 marks 를 가진 글자들을 Tiptap text node 들로 묶음.
 */
function buildParagraphContent(
  paragraphText: string,
  charMarkMap: Map<number, TiptapTextMark[]>
): TiptapTextNode[] {
  if (!paragraphText) return [];

  const nodes: TiptapTextNode[] = [];
  let cursor = 0;

  while (cursor < paragraphText.length) {
    const currentMarks = charMarkMap.get(cursor) ?? [];
    const currentMarksKey = JSON.stringify(currentMarks);

    // 동일 marks 연속 구간 찾기
    let end = cursor + 1;
    while (end < paragraphText.length) {
      const nextMarks = charMarkMap.get(end) ?? [];
      if (JSON.stringify(nextMarks) !== currentMarksKey) break;
      end++;
    }

    const text = paragraphText.slice(cursor, end);
    const node: TiptapTextNode = { type: "text", text };
    if (currentMarks.length > 0) {
      node.marks = currentMarks;
    }
    nodes.push(node);
    cursor = end;
  }

  return nodes;
}

/**
 * annotationsToTiptapDoc — SyntaxAnnotation[] → Tiptap JSON doc
 *
 * 에디터가 만드는 doc 과 동일한 구조를 서버에서 재현.
 * generateHTML() 에 전달해 HTML 출력 생성.
 */
export function annotationsToTiptapDoc(
  passage: PassageForRender,
  annotations: SyntaxAnnotation[]
): TiptapDoc {
  const paragraphs = passage.paragraphs.length > 0 ? passage.paragraphs : [passage.body_text];

  const paragraphLengths = paragraphs.map((p) => p.length);
  const markMap = buildMarkMap(annotations, paragraphLengths);

  const paragraphNodes: TiptapParagraphNode[] = paragraphs.map((paraText, i) => {
    const paraMarkMap = markMap.get(i) ?? new Map();
    const content = buildParagraphContent(paraText, paraMarkMap);
    return {
      type: "paragraph",
      content: content.length > 0 ? content : undefined,
    };
  });

  return {
    type: "doc",
    content: paragraphNodes,
  };
}
