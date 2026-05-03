/**
 * BottomLabelMark — 본문 아래 한 글자 약어 extension (AnnotationKind.BOTTOM_LABEL)
 *
 * 문장 성분 약어 (예: "S", "V", "O", "OC", "SC") 를 대상 span 아래에 표시한다.
 * P1-2 에서 실제 렌더링 로직을 추가한다.
 *
 * 이 스텁 구현은 "등록 + 직렬화 라우팅" 만 제공한다.
 * - HTML 렌더링: <span data-bottom-label-text="...">
 * - P1-2 에서 nodeView/decoration 으로 교체 예정
 *
 * NOTE: AnnotationKind.BOTTOM_LABEL 의 TypeScript 미러 값 = "bottom_label"
 * (shared/schemas/annotation.py AnnotationKind.BOTTOM_LABEL = "bottom_label")
 * Python schema 변경 시 ANNOTATION_KIND 상수 파일도 동기화 필요.
 */
import { Mark, mergeAttributes } from "@tiptap/core";

export interface BottomLabelOptions {
  HTMLAttributes: Record<string, unknown>;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    bottomLabel: {
      /**
       * 선택 범위에 하단 라벨을 설정한다.
       */
      setBottomLabel: (attrs: {
        text: string;
        colorIndex?: number;
        category?: string | null;
      }) => ReturnType;
      /**
       * 선택 범위의 하단 라벨을 해제한다.
       */
      unsetBottomLabel: () => ReturnType;
    };
  }
}

export const BottomLabelMark = Mark.create<BottomLabelOptions>({
  name: "bottomLabel",

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      text: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-bottom-label-text"),
        renderHTML: (attributes) => {
          if (!attributes.text) return {};
          return { "data-bottom-label-text": attributes.text as string };
        },
      },
      colorIndex: {
        default: null,
        parseHTML: (element) => {
          const v = element.getAttribute("data-bottom-label-color");
          return v != null ? Number(v) : null;
        },
        renderHTML: (attributes) => {
          if (attributes.colorIndex == null) return {};
          return {
            "data-bottom-label-color": String(attributes.colorIndex as number),
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
    };
  },

  parseHTML() {
    return [{ tag: "span[data-bottom-label-text]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        "data-annotation-kind": "bottom_label",
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setBottomLabel:
        (attrs) =>
        ({ commands }) => {
          return commands.setMark(this.name, attrs);
        },
      unsetBottomLabel:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name);
        },
    };
  },
});
