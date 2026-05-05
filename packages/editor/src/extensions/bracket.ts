/**
 * BracketMark — 괄호 표시 extension (AnnotationKind.BRACKET)
 *
 * 구문 덩어리를 괄호로 묶는다. 괄호 모양은"()", "{}", "[]", "⌜⌟", "<>" 5종.
 *
 * ## 렌더링 방식 (NG-2 fix)
 *
 * 기존 CSS ::before / ::after pseudo-element 방식은 highlight/underline 과 같은 span 에
 * 겹칠 때 ProseMirror 가 bracket span 을 텍스트 노드 경계마다 분할하면서 모든 조각에
 * ::before / ::after 가 붙어 `(I)(am a)(boy)` 처럼 괄호가 중복 렌더되는 버그가 있었다.
 *
 * 수정: ProseMirror Plugin (addProseMirrorPlugins) 으로 Decoration.widget 을 사용한다.
 *   - bracket mark 의 annotationId 별로 전체 범위 (from, to) 를 추적한다.
 *   - from 위치에 여는 괄호 widget, to 위치에 닫는 괄호 widget 을 삽입한다.
 *   - mark 분할과 무관하게 항상 정확히 양 끝에만 괄호가 렌더된다.
 *
 * CSS 는 bracket span 의 배경/테두리 색상 표시에만 사용한다 (::before / ::after 제거).
 *
 * NOTE: AnnotationKind.BRACKET 의 TypeScript 미러 값 = "bracket"
 * (shared/schemas/annotation.py AnnotationKind.BRACKET = "bracket")
 * Python schema 변경 시 ANNOTATION_KIND 상수 파일도 동기화 필요.
 */
import { Mark, mergeAttributes } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

// P1-10c: ⌜⌟ / <> 추가 — Decoration.widget 방식으로 실제 DOM 에 삽입
export type BracketStyle = "()" | "{}" | "[]" | "⌜⌟" | "<>";

export interface BracketOptions {
  HTMLAttributes: Record<string, unknown>;
}

/** bracketStyle 에 대응하는 여는/닫는 괄호 문자 쌍 (테스트용 export) */
export const BRACKET_CHARS: Record<BracketStyle, [string, string]> = {
  "()": ["(", ")"],
  "{}": ["{", "}"],
  "[]": ["[", "]"],
  "⌜⌟": ["⌜", "⌟"],
  "<>": ["<", ">"],
};

/** colorIndex → CSS 변수명 (EditorPoc.css --anno-color-N 과 동기화) */
function colorVar(colorIndex: number | null): string {
  if (colorIndex == null || colorIndex < 1 || colorIndex > 12) return "var(--anno-color-0)";
  return `var(--anno-color-${colorIndex})`;
}

/** bracket Decoration.widget 용 DOM 요소 생성 */
function makeBracketWidget(char: string, colorIndex: number | null): HTMLElement {
  const span = document.createElement("span");
  span.setAttribute("data-bracket-widget", "true");
  span.style.color = colorVar(colorIndex);
  span.style.fontWeight = "700";
  // 줄바꿈 방지: 여는 괄호가 줄 끝에 혼자 남지 않도록
  span.style.whiteSpace = "nowrap";
  span.textContent = char;
  return span;
}

const bracketPluginKey = new PluginKey("bracketDecorations");

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

  /**
   * ProseMirror Plugin — bracket Decoration.widget
   *
   * doc 내 모든 bracket mark 를 순회해 annotationId 별 (from, to) 범위를 계산한 뒤,
   * from 위치에 여는 괄호 widget, to 위치에 닫는 괄호 widget 을 삽입한다.
   *
   * 이 방식은 highlight/underline 과 같은 span 에 겹쳐도 mark 분할과 무관하게
   * 정확히 양 끝에만 괄호가 렌더된다 (NG-2 fix).
   */
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: bracketPluginKey,
        props: {
          decorations(state) {
            const { doc } = state;

            // annotationId → { from, to, bracketStyle, colorIndex }
            const bracketMap = new Map<
              string,
              { from: number; to: number; bracketStyle: BracketStyle; colorIndex: number | null }
            >();

            // annotationId 없는 bracket (레거시 / annotationId 누락) 별도 처리
            const anonBrackets: Array<{
              from: number;
              to: number;
              bracketStyle: BracketStyle;
              colorIndex: number | null;
            }> = [];

            doc.descendants((node, pos) => {
              if (!node.isText) return;
              for (const mark of node.marks) {
                if (mark.type.name !== "bracket") continue;
                const style = (mark.attrs.bracketStyle as BracketStyle | null) ?? "()";
                const colorIdx = (mark.attrs.colorIndex as number | null) ?? null;
                const annId = (mark.attrs.annotationId as string | null | undefined) ?? null;
                const nodeFrom = pos;
                const nodeTo = pos + node.nodeSize;

                if (!annId) {
                  anonBrackets.push({
                    from: nodeFrom,
                    to: nodeTo,
                    bracketStyle: style,
                    colorIndex: colorIdx,
                  });
                  continue;
                }

                const existing = bracketMap.get(annId);
                if (!existing) {
                  bracketMap.set(annId, {
                    from: nodeFrom,
                    to: nodeTo,
                    bracketStyle: style,
                    colorIndex: colorIdx,
                  });
                } else {
                  bracketMap.set(annId, {
                    from: Math.min(existing.from, nodeFrom),
                    to: Math.max(existing.to, nodeTo),
                    bracketStyle: style,
                    colorIndex: colorIdx,
                  });
                }
              }
            });

            const decorations: Decoration[] = [];

            function addBracketDecorations(entry: {
              from: number;
              to: number;
              bracketStyle: BracketStyle;
              colorIndex: number | null;
            }) {
              const chars = BRACKET_CHARS[entry.bracketStyle] ?? ["(", ")"];
              const openEl = makeBracketWidget(chars[0], entry.colorIndex);
              const closeEl = makeBracketWidget(chars[1], entry.colorIndex);
              // side: -1 → 커서가 양 끝에 있을 때 widget 바깥쪽 우선
              decorations.push(
                Decoration.widget(entry.from, openEl, {
                  side: -1,
                  key: `bracket-open-${entry.from}`,
                }),
                Decoration.widget(entry.to, closeEl, {
                  side: 1,
                  key: `bracket-close-${entry.to}`,
                })
              );
            }

            for (const entry of bracketMap.values()) {
              addBracketDecorations(entry);
            }
            for (const entry of anonBrackets) {
              addBracketDecorations(entry);
            }

            return DecorationSet.create(doc, decorations);
          },
        },
      }),
    ];
  },
});
