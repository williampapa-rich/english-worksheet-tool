/**
 * ArrowMark — 화살표 extension (AnnotationKind.ARROW)
 *
 * 단어 간 의미 관계를 화살표로 표시한다.
 * CLAUDE.md §3.5 에서 "ArrowDecoration — 화살표 (Decoration API, 텍스트와 별개의 레이어)"
 * 로 명시되어 있다. P1-2 에서 ProseMirror Decoration API 로 전환할 예정.
 *
 * 이 스텁 구현은 "등록 + 직렬화 라우팅" 만 제공한다. 직렬화 형식:
 *   - span: 화살표 출발점 (SyntaxAnnotation.span)
 *   - arrowTargetStart / arrowTargetEnd: 화살표 도착점 char offset
 *     (SyntaxAnnotation.arrow_target_span)
 *
 * 설계 메모 (P1-2 에서 결정할 것):
 *   화살표는 두 span 을 연결하는 비-선형 관계다. Mark API 는 단일 span 에 bound 되어
 *   있으므로 도착점 span 을 attributes 로 기록하는 방식으로 우회한다.
 *   렌더링은 Decoration API 또는 SVG overlay 로 P1-2 에서 확정.
 *
 * NOTE: AnnotationKind.ARROW 의 TypeScript 미러 값 = "arrow"
 * (shared/schemas/annotation.py AnnotationKind.ARROW = "arrow")
 * Python schema 변경 시 ANNOTATION_KIND 상수 파일도 동기화 필요.
 */
import { Mark, mergeAttributes } from "@tiptap/core";

export interface ArrowOptions {
  HTMLAttributes: Record<string, unknown>;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    arrow: {
      /**
       * 선택 범위에 화살표 마크를 설정한다.
       * arrowTargetStart / arrowTargetEnd 는 도착점의 character offset.
       */
      setArrow: (attrs: {
        arrowTargetStart: number;
        arrowTargetEnd: number;
        colorIndex?: number;
        category?: string | null;
        annotationId?: string | null;
      }) => ReturnType;
      /**
       * 선택 범위의 화살표 마크를 해제한다.
       */
      unsetArrow: () => ReturnType;
    };
  }
}

export const ArrowMark = Mark.create<ArrowOptions>({
  name: "arrow",

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      arrowTargetStart: {
        default: null,
        parseHTML: (element) => {
          const v = element.getAttribute("data-arrow-target-start");
          return v != null ? Number(v) : null;
        },
        renderHTML: (attributes) => {
          if (attributes.arrowTargetStart == null) return {};
          return {
            "data-arrow-target-start": String(attributes.arrowTargetStart as number),
          };
        },
      },
      arrowTargetEnd: {
        default: null,
        parseHTML: (element) => {
          const v = element.getAttribute("data-arrow-target-end");
          return v != null ? Number(v) : null;
        },
        renderHTML: (attributes) => {
          if (attributes.arrowTargetEnd == null) return {};
          return {
            "data-arrow-target-end": String(attributes.arrowTargetEnd as number),
          };
        },
      },
      colorIndex: {
        default: null,
        parseHTML: (element) => {
          const v = element.getAttribute("data-arrow-color");
          return v != null ? Number(v) : null;
        },
        renderHTML: (attributes) => {
          if (attributes.colorIndex == null) return {};
          return {
            "data-arrow-color": String(attributes.colorIndex as number),
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
    return [{ tag: "span[data-arrow-target-start]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        "data-annotation-kind": "arrow",
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setArrow:
        (attrs) =>
        ({ commands }) => {
          return commands.setMark(this.name, attrs);
        },
      unsetArrow:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name);
        },
    };
  },
});
