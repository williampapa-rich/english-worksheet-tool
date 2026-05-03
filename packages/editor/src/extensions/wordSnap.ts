/**
 * WordSnapExtension — 띄어쓰기 경계 단위 선택 스냅
 *
 * ProseMirror Plugin 의 appendTransaction 을 사용해 selection 변경 시
 * from / to 양 끝점을 가장 가까운 단어 경계(띄어쓰기 기준)로 자동 확장한다.
 *
 * 동작 기준:
 * - 단어: 연속된 비공백 문자 덩어리. 구두점 포함.
 * - from: 단어 시작 위치로 snap (왼쪽 확장).
 * - to: 단어 끝 위치로 snap (오른쪽 확장).
 * - cursor(empty selection) 는 스냅하지 않음.
 * - 이미 단어 경계에 정확히 걸쳐 있으면 변경 없음.
 *
 * 참고: docs/reference-program-analysis.md §7.4 PM 결정 (hard snap, 띄어쓰기 토큰).
 */
import { Extension } from "@tiptap/core";
import type { Node as PmNode } from "@tiptap/pm/model";
import { Plugin, PluginKey, TextSelection } from "@tiptap/pm/state";

const wordSnapKey = new PluginKey("wordSnap");

/**
 * 텍스트 내에서 주어진 offset 을 포함하는 단어의 [start, end] 를 반환한다.
 * offset 이 공백 위에 있거나 단어가 없으면 null 을 반환한다.
 */
function wordBoundaryAround(text: string, offset: number): [number, number] | null {
  // offset 이 현재 공백을 가리키고 있고 양쪽도 공백이면 단어 없음
  const atSpaceRight = offset < text.length && /\s/.test(text[offset] ?? "");
  const atSpaceLeft = offset > 0 && /\s/.test(text[offset - 1] ?? "");
  if (atSpaceRight && atSpaceLeft) return null;
  // offset 이 공백 바로 뒤(왼쪽이 공백)이고 오른쪽도 공백이면 단어 없음
  if (offset === text.length && atSpaceLeft) return null;

  // 단어 시작: offset 에서 왼쪽으로 공백/시작 만날 때까지
  let start = offset;
  while (start > 0 && !/\s/.test(text[start - 1] ?? "")) {
    start--;
  }

  // 단어 끝: offset 에서 오른쪽으로 공백/끝 만날 때까지
  let end = offset;
  while (end < text.length && !/\s/.test(text[end] ?? "")) {
    end++;
  }

  if (start === end) return null;
  return [start, end];
}

/**
 * ProseMirror document 에서 절대 pos 를 단어 경계로 스냅한다.
 * snapDir: "start" = 왼쪽(단어 시작)으로, "end" = 오른쪽(단어 끝)으로 확장.
 */
function snapPosToWord(doc: PmNode, pos: number, snapDir: "start" | "end"): number {
  const resolved = doc.resolve(pos);
  const parentOffset = resolved.parentOffset;
  const parent = resolved.parent;

  // 부모 블록 노드의 텍스트를 수집
  let text = "";
  for (let i = 0; i < parent.childCount; i++) {
    const child = parent.child(i);
    if (child.isText && child.text != null) {
      text += child.text;
    } else {
      // 비 텍스트 노드(inline node 등)는 단어 경계로 취급
      text += " ";
    }
  }

  const boundary = wordBoundaryAround(text, parentOffset);
  if (!boundary) return pos;

  const [wordStart, wordEnd] = boundary;
  const targetParentOffset = snapDir === "start" ? wordStart : wordEnd;
  return resolved.start() + targetParentOffset;
}

export const WordSnapExtension = Extension.create({
  name: "wordSnap",

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: wordSnapKey,
        appendTransaction(transactions, _oldState, newState) {
          // selection 변경이 없는 트랜잭션은 무시
          const selChanged = transactions.some((tr) => tr.selectionSet);
          if (!selChanged) return null;

          const sel = newState.selection;
          // cursor (empty selection) 는 스냅 안 함
          if (sel.empty) return null;

          // TextSelection 만 처리
          if (!(sel instanceof TextSelection)) return null;

          const { $from, $to } = sel;
          const doc = newState.doc;

          const snappedFrom = snapPosToWord(doc, $from.pos, "start");
          const snappedTo = snapPosToWord(doc, $to.pos, "end");

          // 변경 없으면 null 반환 (무한 루프 방지)
          if (snappedFrom === $from.pos && snappedTo === $to.pos) return null;

          const newSel = TextSelection.create(doc, snappedFrom, snappedTo);
          return newState.tr.setSelection(newSel);
        },
      }),
    ];
  },
});
