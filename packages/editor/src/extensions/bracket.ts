/**
 * BracketMark — 괄호 표시 extension (AnnotationKind.BRACKET)
 *
 * 구문 덩어리를 괄호로 묶는다. 괄호 모양은 "()", "{}", "[]" 3종.
 * P1-2 에서 괄호 시각화 렌더링을 추가한다.
 *
 * 이 스텁 구현은 "등록 + 직렬화 라우팅" 만 제공한다.
 *
 * 설계 메모 (ADR-0004 follow-up §1):
 *   bracket 은 mark 가 아니라 Decoration 또는 nodeView 후보라고 ADR-0004 에서 언급됨.
 *   P1-2 에서 실제 렌더링 방식을 결정한다. 스텁 단계에서는 mark 로 등록해
 *   직렬화 라우팅만 확보한다.
 *
 * NOTE: AnnotationKind.BRACKET 의 TypeScript 미러 값 = "bracket"
 * (shared/schemas/annotation.py AnnotationKind.BRACKET = "bracket")
 * Python schema 변경 시 ANNOTATION_KIND 상수 파일도 동기화 필요.
 */
import { Mark, mergeAttributes } from "@tiptap/core";

// P1-10c: ⌜⌟ / <> 추가 — Unicode 글자를 inline run 으로 삽입하는 방식
export type BracketStyle = "()" | "{}" | "[]" | "⌜⌟" | "<>";

export interface BracketOptions {
  HTMLAttributes: Record<string, unknown>;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    bracket: {
      /**
       * 선택 범위에 괄호 마크를 설정한다.
       */
      setBracket: (attrs: {
        bracketStyle: BracketStyle;
        colorIndex?: number;
        category?: string | null;
        annotationId?: string | null;
      }) => ReturnType;
      /**
       * 선택 범위의 괄호 마크를 해제한다.
       */
      unsetBracket: () => ReturnType;
    };
  }
}

export const BracketMark = Mark.create<BracketOptions>({
  name: "bracket",

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      bracketStyle: {
        default: "()",
        parseHTML: (element) => element.getAttribute("data-bracket-style") ?? "()",
        renderHTML: (attributes) => {
          return {
            "data-bracket-style": attributes.bracketStyle as string,
          };
        },
      },
      colorIndex: {
        default: null,
        parseHTML: (element) => {
          const v = element.getAttribute("data-bracket-color");
          return v != null ? Number(v) : null;
        },
        renderHTML: (attributes) => {
          if (attributes.colorIndex == null) return {};
          return {
            "data-bracket-color": String(attributes.colorIndex as number),
            "data-color-index": String(attributes.colorIndex as number),
          };
        },
      },
      category: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-category") ?? null,
        renderHTML: (attributes) => {
          if (!attributes.category) return {};
          return { "data-category": attributes.category as string };
        },
      },
      annotationId: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-annotation-id") ?? null,
        renderHTML: (attributes) => {
          if (!attributes.annotationId) return {};
          return { "data-annotation-id": attributes.annotationId as string };
        },
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-bracket-style]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        "data-annotation-kind": "bracket",
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setBracket:
        (attrs) =>
        ({ commands }) => {
          return commands.setMark(this.name, attrs);
        },
      unsetBracket:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name);
        },
    };
  },
});
