/**
 * markRanges — annotationId 기반 mark range 수집 헬퍼.
 *
 * 동일 annotationId 를 가진 모든 mark range 를 ProseMirror doc 에서 수집한다.
 * 칩 x 버튼 동작 (unset) 에 사용된다.
 *
 * 설계 메모:
 *   ProseMirror 가 mark 를 적용할 때 텍스트 노드 경계에서 자동으로 split 할 수 있다.
 *   같은 annotationId 로 묶인 split 조각들을 모두 수집해 통째 unset 에 사용한다.
 *   이것이 "부분 unset 잔여 마크 버그"를 자연 해결하는 핵심 메커니즘이다.
 */

import type { Node as ProseMirrorNode } from "@tiptap/pm/model";

/**
 * MarkRange — 단일 mark 조각의 ProseMirror position 구간.
 */
export interface MarkRange {
  from: number;
  to: number;
  markName: string; // ProseMirror mark type name (예: "topLabel", "highlight")
}

/**
 * collectMarkRangesByAnnotationId — 동일 annotationId 의 모든 mark range 수집.
 *
 * doc.descendants 를 순회하며 annotationId attr 가 일치하는 mark 를 가진
 * 텍스트 노드의 from/to 를 수집한다.
 *
 * @param doc - ProseMirror Node (editor.state.doc)
 * @param annotationId - 수집 대상 annotationId
 * @returns MarkRange[] — 동일 annotationId 를 가진 모든 mark 의 range 목록
 */
export function collectMarkRangesByAnnotationId(
  doc: ProseMirrorNode,
  annotationId: string
): MarkRange[] {
  const ranges: MarkRange[] = [];

  doc.descendants((node, pos) => {
    if (!node.isText) return;

    for (const mark of node.marks) {
      const attrs = mark.attrs as Record<string, unknown>;
      if (attrs.annotationId === annotationId) {
        ranges.push({
          from: pos,
          to: pos + node.nodeSize,
          markName: mark.type.name,
        });
      }
    }
  });

  return ranges;
}
