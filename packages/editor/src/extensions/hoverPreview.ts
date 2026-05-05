/**
 * HoverPreviewExtension — hover 위치 토큰 미리보기 (Decoration)
 *
 * 마우스를 에디터 본문 위에 올리면 현재 hover 한 토큰(단어 또는 구두점 단위)의
 * 범위에 회색 반투명 음영 Decoration 을 표시한다.
 *
 * 동작:
 * - mousemove 이벤트 → pos at cursor → tokenBoundaryAround 계산 → Decoration 주입
 * - mouseleave 이벤트 → Decoration 제거
 *
 * 토큰 경계 규칙은 WordSnapExtension 과 동일 (단어 + 구두점 분리, 어포스트로피 예외).
 *
 * 구현 선택 (CLAUDE.md §3.6):
 * - ProseMirror Decoration API — 실제 selection 변경 없이 시각만 표시.
 *   CSS :hover 만으로는 "단어 단위" 음영이 불가능 (브라우저가 char/word 경계를 모름).
 *   Decoration 이 가장 자연스럽고 Tiptap 공식 Extension API 안에서 처리 가능.
 *
 * P1-followup-ng-fixes NG 1b 해석 A.
 */
import { Extension } from "@tiptap/core";
import type { Node as PmNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

const hoverPreviewKey = new PluginKey<DecorationSet>("hoverPreview");

// ---------------------------------------------------------------------------
// 토큰 경계 (WordSnapExtension 와 동일 로직)
// ---------------------------------------------------------------------------

function isWordChar(ch: string): boolean {
  return /[a-zA-Z0-9''']/.test(ch);
}

function isSpace(ch: string): boolean {
  return /\s/.test(ch);
}

function tokenBoundaryAround(text: string, offset: number): [number, number] | null {
  if (offset >= text.length) {
    if (offset === 0) return null;
    const leftCh = text[offset - 1] ?? "";
    if (isSpace(leftCh)) return null;
    if (isWordChar(leftCh)) {
      let start = offset - 1;
      while (start > 0 && isWordChar(text[start - 1] ?? "")) start--;
      return [start, offset];
    }
    return [offset - 1, offset];
  }
  const ch = text[offset] ?? "";
  if (isSpace(ch)) return null;
  if (isWordChar(ch)) {
    let start = offset;
    while (start > 0 && isWordChar(text[start - 1] ?? "")) start--;
    let end = offset;
    while (end < text.length && isWordChar(text[end] ?? "")) end++;
    return [start, end];
  }
  return [offset, offset + 1];
}

/**
 * ProseMirror document 에서 절대 pos 기준 토큰 [from, to] 를 반환한다.
 */
function tokenRangeAt(doc: PmNode, pos: number): { from: number; to: number } | null {
  const resolved = doc.resolve(pos);
  const parentOffset = resolved.parentOffset;
  const parent = resolved.parent;

  let text = "";
  for (let i = 0; i < parent.childCount; i++) {
    const child = parent.child(i);
    if (child.isText && child.text != null) {
      text += child.text;
    } else {
      text += " ";
    }
  }

  const boundary = tokenBoundaryAround(text, parentOffset);
  if (!boundary) return null;

  const blockStart = resolved.start();
  return { from: blockStart + boundary[0], to: blockStart + boundary[1] };
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export const HoverPreviewExtension = Extension.create({
  name: "hoverPreview",

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: hoverPreviewKey,

        state: {
          init() {
            return DecorationSet.empty;
          },
          apply(tr, decorationSet) {
            // meta 로 전달된 새 DecorationSet 으로 교체
            const meta = tr.getMeta(hoverPreviewKey) as DecorationSet | null | undefined;
            if (meta !== undefined && meta !== null) return meta;
            if (meta === null) return DecorationSet.empty;
            // doc 변경 시 위치 매핑
            return decorationSet.map(tr.mapping, tr.doc);
          },
        },

        props: {
          decorations(state) {
            return hoverPreviewKey.getState(state) ?? DecorationSet.empty;
          },

          handleDOMEvents: {
            mousemove(view, event) {
              const mouseEvent = event as MouseEvent;
              const pos = view.posAtCoords({
                left: mouseEvent.clientX,
                top: mouseEvent.clientY,
              });
              if (!pos) {
                // 에디터 영역 벗어남 → 제거
                const tr = view.state.tr.setMeta(hoverPreviewKey, null);
                view.dispatch(tr);
                return false;
              }

              const range = tokenRangeAt(view.state.doc, pos.pos);
              if (!range) {
                const tr = view.state.tr.setMeta(hoverPreviewKey, null);
                view.dispatch(tr);
                return false;
              }

              // 현재 Decoration 과 동일 범위면 불필요한 dispatch 생략
              const currentSet = hoverPreviewKey.getState(view.state) ?? DecorationSet.empty;
              const existing = currentSet.find(range.from, range.to);
              if (
                existing.length === 1 &&
                existing[0] &&
                existing[0].from === range.from &&
                existing[0].to === range.to
              ) {
                return false;
              }

              const decoration = Decoration.inline(range.from, range.to, {
                class: "hover-token-preview",
              });
              const newSet = DecorationSet.create(view.state.doc, [decoration]);
              const tr = view.state.tr.setMeta(hoverPreviewKey, newSet);
              view.dispatch(tr);
              return false;
            },

            mouseleave(view) {
              const tr = view.state.tr.setMeta(hoverPreviewKey, null);
              view.dispatch(tr);
              return false;
            },
          },
        },
      }),
    ];
  },
});
