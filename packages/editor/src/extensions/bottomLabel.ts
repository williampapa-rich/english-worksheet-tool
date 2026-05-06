/**
 * BottomLabelMark — 본문 아래 한 글자 약어 extension (AnnotationKind.BOTTOM_LABEL)
 *
 * 문장 성분 약어 (예: "S", "V", "O", "OC", "SC") 를 대상 span 아래에 표시한다.
 *
 * ## 렌더링 방식 (NG-4 fix)
 *
 * 기존 CSS ::after pseudo-element 방식은 highlight/underline 과 같은 span 에
 * 겹칠 때 ProseMirror 가 bottomLabel span 을 텍스트 노드 경계마다 분할하면서 모든
 * 조각에 ::after 가 붙어 라벨 텍스트가 중복 렌더되는 버그가 있었다.
 * 또한 display: inline-block 이 부모 underline 마크의 text-decoration 전파를
 * 차단해 underline 이 렌더되지 않는 버그도 있었다 (NG-3).
 *
 * 수정: ProseMirror Plugin (addProseMirrorPlugins) 으로 Decoration.widget 을 사용한다.
 *   - bottomLabel mark 의 annotationId 별로 전체 범위 (from, to) 를 추적한다.
 *   - to 위치에 라벨+하단 보더라인을 담은 widget 을 삽입한다.
 *   - mark 분할과 무관하게 항상 정확히 span 끝 지점에만 라벨이 렌더된다.
 *
 * CSS 는 bottomLabel span 의 하단 보더라인 표시에만 사용한다 (::after 제거).
 *
 * NOTE: AnnotationKind.BOTTOM_LABEL 의 TypeScript 미러 값 = "bottom_label"
 * (shared/schemas/annotation.py AnnotationKind.BOTTOM_LABEL = "bottom_label")
 * Python schema 변경 시 ANNOTATION_KIND 상수 파일도 동기화 필요.
 */
import { Mark, mergeAttributes } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { colorVar } from "./colorUtils";

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
        annotationId?: string | null;
      }) => ReturnType;
      /**
       * 선택 범위의 하단 라벨을 해제한다.
       */
      unsetBottomLabel: () => ReturnType;
    };
  }
}

const bottomLabelPluginKey = new PluginKey("bottomLabelDecorations");

/**
 * bottom_label Decoration.widget 용 DOM 요소 생성.
 * 라벨 텍스트 + 하단 보더라인을 포함하는 wrapper span 을 반환한다.
 */
function makeBottomLabelWidget(text: string, colorIndex: number | null): HTMLElement {
  const wrapper = document.createElement("span");
  wrapper.setAttribute("data-bottom-label-widget", "true");
  wrapper.style.position = "relative";
  wrapper.style.display = "inline-block";
  wrapper.style.lineHeight = "1";
  wrapper.style.paddingBottom = "1px";
  wrapper.style.marginBottom = "calc(0.84em - 0.9px)";
  wrapper.style.borderBottom = `2px solid ${colorVar(colorIndex)}`;
  wrapper.style.userSelect = "none";
  wrapper.style.pointerEvents = "none";

  const label = document.createElement("span");
  label.setAttribute("data-bottom-label-text-widget", "true");
  label.style.position = "absolute";
  label.style.bottom = "calc(-1.1em - 3px)";
  label.style.left = "50%";
  label.style.transform = "translateX(-50%)";
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

  /**
   * ProseMirror Plugin — bottom_label Decoration.widget
   *
   * doc 내 모든 bottomLabel mark 를 순회해 annotationId 별 (from, to) 범위를 계산한 뒤,
   * to 위치에 라벨+보더라인 widget 을 삽입한다.
   *
   * 이 방식은 highlight/underline 과 같은 span 에 겹쳐도 mark 분할과 무관하게
   * 정확히 span 끝에만 라벨이 렌더된다 (NG-4 fix).
   * display: inline-block 을 mark span 에서 제거하므로 underline 전파도 정상화된다 (NG-3 fix).
   */
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: bottomLabelPluginKey,
        props: {
          decorations(state) {
            const { doc } = state;

            // annotationId → { from, to, text, colorIndex }
            const labelMap = new Map<
              string,
              { from: number; to: number; text: string; colorIndex: number | null }
            >();

            // annotationId 없는 bottomLabel (레거시 / 누락) 별도 처리
            const anonLabels: Array<{
              from: number;
              to: number;
              text: string;
              colorIndex: number | null;
            }> = [];

            doc.descendants((node, pos) => {
              if (!node.isText) return;
              for (const mark of node.marks) {
                if (mark.type.name !== "bottomLabel") continue;
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

            // anonLabels 는 annotationId 가 없으므로 위치 기반 index 로 key 생성
            let anonIndex = 0;

            function addLabelDecoration(
              entry: {
                to: number;
                text: string;
                colorIndex: number | null;
              },
              annotationId: string | null
            ) {
              if (!entry.text) return;
              const el = makeBottomLabelWidget(entry.text, entry.colorIndex);
              // annotationId 포함으로 동일 위치 겹침 시 key 충돌 방지 (#1 fix)
              const idSegment = annotationId ?? `anon-${anonIndex++}`;
              decorations.push(
                Decoration.widget(entry.to, el, {
                  side: 1,
                  key: `bottom-label-${idSegment}-${entry.to}`,
                })
              );
            }

            for (const [annId, entry] of labelMap.entries()) {
              addLabelDecoration(entry, annId);
            }
            for (const entry of anonLabels) {
              addLabelDecoration(entry, null);
            }

            return DecorationSet.create(doc, decorations);
          },
        },
      }),
    ];
  },
});
