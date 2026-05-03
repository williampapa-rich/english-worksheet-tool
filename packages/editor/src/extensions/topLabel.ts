/**
 * TopLabelMark — 본문 위 라벨 extension (AnnotationKind.TOP_LABEL)
 *
 * 구문 역할 라벨 (예: "S", "V", "=동명사주어", "(부사구)") 을 대상 span 위에
 * 표시한다. P1-2 에서 실제 렌더링 로직을 추가한다.
 *
 * 이 스텁 구현은 "등록 + 직렬화 라우팅" 만 제공한다.
 * - HTML 렌더링: <span data-top-label="..."> (P1-2에서 nodeView/decoration으로 교체 예정)
 * - getAttrs: data-top-label 속성에서 text, colorIndex 를 복원
 *
 * NOTE: AnnotationKind.TOP_LABEL 의 TypeScript 미러 값 = "top_label"
 * (shared/schemas/annotation.py AnnotationKind.TOP_LABEL = "top_label")
 * Python schema 변경 시 ANNOTATION_KIND 상수 파일도 동기화 필요.
 */
import { Mark, mergeAttributes } from "@tiptap/core";

export interface TopLabelOptions {
  HTMLAttributes: Record<string, unknown>;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    topLabel: {
      /**
       * 선택 범위에 상단 라벨을 설정한다.
       */
      setTopLabel: (attrs: { text: string; colorIndex?: number }) => ReturnType;
      /**
       * 선택 범위의 상단 라벨을 해제한다.
       */
      unsetTopLabel: () => ReturnType;
    };
  }
}

export const TopLabelMark = Mark.create<TopLabelOptions>({
  name: "topLabel",

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      text: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-top-label-text"),
        renderHTML: (attributes) => {
          if (!attributes.text) return {};
          return { "data-top-label-text": attributes.text as string };
        },
      },
      colorIndex: {
        default: null,
        parseHTML: (element) => {
          const v = element.getAttribute("data-top-label-color");
          return v != null ? Number(v) : null;
        },
        renderHTML: (attributes) => {
          if (attributes.colorIndex == null) return {};
          return {
            "data-top-label-color": String(attributes.colorIndex as number),
          };
        },
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-top-label-text]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        "data-annotation-kind": "top_label",
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setTopLabel:
        (attrs) =>
        ({ commands }) => {
          return commands.setMark(this.name, attrs);
        },
      unsetTopLabel:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name);
        },
    };
  },
});
