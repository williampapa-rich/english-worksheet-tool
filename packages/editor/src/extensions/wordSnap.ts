/**
 * WordSnapExtension — 단어/구두점 경계 단위 선택 스냅
 *
 * ProseMirror Plugin 의 appendTransaction 을 사용해 selection 변경 시
 * from / to 양 끝점을 가장 가까운 토큰 경계로 자동 확장한다.
 *
 * 동작 기준:
 * - 토큰 종류 1: 알파벳+숫자+어포스트로피 연속 (단어). 예: "don't", "it's", "score"
 *   - 단어 내 어포스트로피 (don't, it's) 는 단어 일부로 유지.
 *   - 단, 따옴표 역할의 앞뒤 따옴표 ("…", '…') 는 별도 구두점 토큰.
 * - 토큰 종류 2: 구두점 단독 토큰 (1글자씩). 예: ",", ".", ";", ":", "!", "?",
 *   "(", ")", "[", "]", "{", "}", '"', '"', '"', '—', '–' 등
 * - 공백 자체는 토큰 없음 (경계 역할만).
 * - from: 토큰 시작 위치로 snap (왼쪽 확장).
 * - to: 토큰 끝 위치로 snap (오른쪽 확장).
 * - cursor(empty selection) 는 스냅하지 않음.
 * - 이미 토큰 경계에 정확히 걸쳐 있으면 변경 없음.
 *
 * 참고: docs/reference-program-analysis.md §7.4 PM 결정 (hard snap, 띄어쓰기 토큰).
 * P1-followup-ng-fixes: NG 1a — 구두점 분리, 어포스트로피 예외.
 */
import { Extension } from "@tiptap/core";
import type { Node as PmNode } from "@tiptap/pm/model";
import { Plugin, PluginKey, TextSelection } from "@tiptap/pm/state";

const wordSnapKey = new PluginKey("wordSnap");

/**
 * 단어 구성 문자 여부:
 * - 영문자 / 숫자 / 어포스트로피(') — 단어 내 어포스트로피 포함.
 * - Unicode 타이포그래픽 어포스트로피 (’, ‘) 도 포함.
 */
function isWordChar(ch: string): boolean {
  return /[a-zA-Z0-9'‘’]/.test(ch);
}

/**
 * 공백 여부
 */
function isSpace(ch: string): boolean {
  return /\s/.test(ch);
}

/**
 * 텍스트 내에서 주어진 offset 을 포함하는 토큰의 [start, end] 를 반환한다.
 *
 * 토큰 규칙:
 * 1. 공백 위 → null (토큰 없음)
 * 2. 단어 문자(isWordChar) → 좌우로 단어 문자가 연속되는 범위
 * 3. 구두점 (그 외 비공백 문자) → offset 1글자 단독 토큰
 *
 * 특별 케이스:
 * - offset 이 경계(공백 바로 오른쪽 또는 문자열 끝) 에 있을 때:
 *   오른쪽 문자 기준으로 토큰 판정.
 */
function tokenBoundaryAround(text: string, offset: number): [number, number] | null {
  // 문자열 끝 또는 공백 위치 처리
  if (offset >= text.length) {
    // 끝 위치 — 왼쪽 문자 기준
    if (offset === 0) return null;
    const leftCh = text[offset - 1] ?? "";
    if (isSpace(leftCh)) return null;
    if (isWordChar(leftCh)) {
      // 단어 토큰 끝에 있음 — 왼쪽으로 확장
      let start = offset - 1;
      while (start > 0 && isWordChar(text[start - 1] ?? "")) start--;
      return [start, offset];
    }
    // 구두점 끝
    return [offset - 1, offset];
  }

  const ch = text[offset] ?? "";

  if (isSpace(ch)) {
    // 공백 위 → null
    return null;
  }

  if (isWordChar(ch)) {
    // 단어 토큰: 좌우로 단어 문자 확장
    let start = offset;
    while (start > 0 && isWordChar(text[start - 1] ?? "")) start--;
    let end = offset;
    while (end < text.length && isWordChar(text[end] ?? "")) end++;
    return [start, end];
  }

  // 구두점: 해당 offset 1글자만 토큰
  return [offset, offset + 1];
}

/**
 * ProseMirror document 에서 절대 pos 를 토큰 경계로 스냅한다.
 * snapDir: "start" = 왼쪽(토큰 시작)으로, "end" = 오른쪽(토큰 끝)으로 확장.
 */
function snapPosToToken(doc: PmNode, pos: number, snapDir: "start" | "end"): number {
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
      // 비 텍스트 노드(inline node 등)는 토큰 경계로 취급 (공백 대체)
      text += " ";
    }
  }

  const boundary = tokenBoundaryAround(text, parentOffset);
  if (!boundary) return pos;

  const [tokenStart, tokenEnd] = boundary;
  const targetParentOffset = snapDir === "start" ? tokenStart : tokenEnd;
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

          const snappedFrom = snapPosToToken(doc, $from.pos, "start");
          const snappedTo = snapPosToToken(doc, $to.pos, "end");

          // 변경 없으면 null 반환 (무한 루프 방지)
          if (snappedFrom === $from.pos && snappedTo === $to.pos) return null;

          const newSel = TextSelection.create(doc, snappedFrom, snappedTo);
          return newState.tr.setSelection(newSel);
        },
      }),
    ];
  },
});
