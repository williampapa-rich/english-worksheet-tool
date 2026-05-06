/**
 * TopLabelMark — 본문 위 라벨 extension (AnnotationKind.TOP_LABEL)
 *
 * 구문 역할 라벨 (예: "S", "V", "=동명사주어", "(부사구)") 을 대상 span 위에
 * 표시한다.
 *
 * ## 렌더링 방식 (NG-4 fix)
 *
 * 기존 CSS ::before pseudo-element 방식은 highlight/underline 과 같은 span 에
 * 겹칠 때 ProseMirror 가 topLabel span 을 텍스트 노드 경계마다 분할하면서 모든
 * 조각에 ::before 가 붙어 라벨 텍스트가 중복 렌더되는 버그가 있었다.
 * 또한 display: inline-block 이 부모 underline 마크의 text-decoration 전파를
 * 차단해 underline 이 렌더되지 않는 버그도 있었다 (NG-3).
 *
 * 수정: ProseMirror Plugin (addProseMirrorPlugins) 으로 Decoration.widget 을 사용한다.
 *   - topLabel mark 의 annotationId 별로 전체 범위 (from, to) 를 추적한다.
 *   - from 위치에 라벨+상단 보더라인을 담은 widget 을 삽입한다.
 *   - mark 분할과 무관하게 항상 정확히 span 시작 지점에만 라벨이 렌더된다.
 *
 * CSS 는 topLabel span 의 상단 보더라인 표시에만 사용한다 (::before 제거).
 *
 * NOTE: AnnotationKind.TOP_LABEL 의 TypeScript 미러 값 = "top_label"
 * (shared/schemas/annotation.py AnnotationKind.TOP_LABEL = "top_label")
 * Python schema 변경 시 ANNOTATION_KIND 상수 파일도 동기화 필요.
 */
import { Mark, mergeAttributes } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export interface TopLabelOptions {
  HTMLAttributes: Record<string, unknown>;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    topLabel: {
      /**
       * 선택 범위에 상단 라벨을 설정한다.
       */
      setTopLabel: (attrs: {
        text: string;
        colorIndex?: number;
        category?: string | null;
        annotationId?: string | null;
      }) => ReturnType;
      /**
       * 선택 범위의 상단 라벨을 해제한다.
       */
      unsetTopLabel: () => ReturnType;
    };
  }
}

/** colorIndex → CSS 변수명 (EditorPoc.css --anno-color-N 과 동기화) */
function colorVar(colorIndex: number | null): string {
  if (colorIndex == null || colorIndex < 1 || colorIndex > 12) return "var(--anno-color-0)";
  return `var(--anno-color-${colorIndex})`;
}

const topLabelPluginKey = new PluginKey("topLabelDecorations");

/**
 * top_label Decoration.widget 용 DOM 요소 생성.
 * 라벨 텍스트 + 상단 보더라인을 포함하는 wrapper span 을 반환한다.
 */
function makeTopLabelWidget(text: string, colorIndex: number | null): HTMLElement {
  const wrapper = document.createElement("span");
  wrapper.setAttribute("data-top-label-widget", "true");
  wrapper.style.position = "relative";
  wrapper.style.display = "inline-block";
  wrapper.style.lineHeight = "1";
  wrapper.style.paddingTop = "1px";
  wrapper.style.marginTop = "calc(0.84em - 0.9px)";
  wrapper.style.borderTop = `2px solid ${colorVar(colorIndex)}`;
  wrapper.style.userSelect = "none";
  wrapper.style.pointerEvents = "none";

  const label = document.createElement("span");
  label.setAttribute("data-top-label-text-widget", "true");
  label.style.position = "absolute";
  label.style.top = "calc(-1.1em - 3px)";
  label.style.left = "0";
  label.style.fontSize = "0.65em";
  label.style.fontWeight = "600";
  label.style.color = "#1e3a5f";
  label.style.padding = "0 3px";
  label.style.whiteSpace = "nowrap";
  label.style.lineHeight = "1.4";
  label.textContent = text;

  wrapper.appendChild(label);
  return wrapper;
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

  /**
   * ProseMirror Plugin — top_label Decoration.widget
   *
   * doc 내 모든 topLabel mark 를 순회해 annotationId 별 (from, to) 범위를 계산한 뒤,
   * from 위치에 라벨+보더라인 widget 을 삽입한다.
   *
   * 이 방식은 highlight/underline 과 같은 span 에 겹쳐도 mark 분할과 무관하게
   * 정확히 span 시작에만 라벨이 렌더된다 (NG-4 fix).
   * display: inline-block 을 mark span 에서 제거하므로 underline 전파도 정상화된다 (NG-3 fix).
   */
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: topLabelPluginKey,
        props: {
          decorations(state) {
            const { doc } = state;

            // annotationId → { from, to, text, colorIndex }
            const labelMap = new Map<
              string,
              { from: number; to: number; text: string; colorIndex: number | null }
            >();

            // annotationId 없는 topLabel (레거시 / 누락) 별도 처리
            const anonLabels: Array<{
              from: number;
              to: number;
              text: string;
              colorIndex: number | null;
            }> = [];

            doc.descendants((node, pos) => {
              if (!node.isText) return;
              for (const mark of node.marks) {
                if (mark.type.name !== "topLabel") continue;
                const text = (mark.attrs.text as string | null) ?? "";
                const colorIdx = (mark.attrs.colorIndex as number | null) ?? null;
                const annId = (mark.attrs.annotationId as string | null | undefined) ?? null;
                const nodeFrom = pos;
                const nodeTo = pos + node.nodeSize;

                if (!annId) {
                  anonLabels.push({ from: nodeFrom, to: nodeTo, text, colorIndex: colorIdx });
                  continue;
                }

                const existing = labelMap.get(annId);
                if (!existing) {
                  labelMap.set(annId, { from: nodeFrom, to: nodeTo, text, colorIndex: colorIdx });
                } else {
                  labelMap.set(annId, {
                    from: Math.min(existing.from, nodeFrom),
                    to: Math.max(existing.to, nodeTo),
                    text,
                    colorIndex: colorIdx,
                  });
                }
              }
            });

            const decorations: Decoration[] = [];

            function addLabelDecoration(entry: {
              from: number;
              text: string;
              colorIndex: number | null;
            }) {
              if (!entry.text) return;
              const el = makeTopLabelWidget(entry.text, entry.colorIndex);
              decorations.push(
                Decoration.widget(entry.from, el, {
                  side: -1,
                  key: `top-label-${entry.from}`,
                })
              );
            }

            for (const entry of labelMap.values()) {
              addLabelDecoration(entry);
            }
            for (const entry of anonLabels) {
              addLabelDecoration(entry);
            }

            return DecorationSet.create(doc, decorations);
          },
        },
      }),
    ];
  },
});
