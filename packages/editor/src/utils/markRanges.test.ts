/**
 * markRanges 단위 테스트 (vitest)
 *
 * collectMarkRangesByAnnotationId 를 ProseMirror Node mock 없이 테스트하기 위해
 * 간단한 ProseMirror-compatible Node stub 을 직접 구성한다.
 */

import type { Mark, Node as ProseMirrorNode } from "@tiptap/pm/model";
import { describe, expect, it } from "vitest";
import type { MarkRange } from "./markRanges";
import { collectMarkRangesByAnnotationId } from "./markRanges";

// ---------------------------------------------------------------------------
// 헬퍼
// ---------------------------------------------------------------------------

function first<T>(arr: T[]): T {
  const item = arr[0];
  if (item === undefined) throw new Error("Expected non-empty array");
  return item;
}

function makeMark(name: string, attrs: Record<string, unknown>): Mark {
  return {
    type: { name },
    attrs,
  } as unknown as Mark;
}

/**
 * makeDocStub — doc.descendants 를 구현하는 최소 stub.
 *
 * descendants 는 각 노드를 순서대로 callback(node, pos) 로 호출한다.
 * boolean | undefined 반환 — ProseMirrorNode.descendants 시그니처 호환.
 */
function makeDocStub(
  nodes: Array<{
    pos: number;
    text: string;
    marks: Mark[];
  }>
): ProseMirrorNode {
  return {
    descendants(callback: (node: ProseMirrorNode, pos: number) => boolean | undefined) {
      for (const n of nodes) {
        const node: ProseMirrorNode = {
          isText: true,
          nodeSize: n.text.length,
          marks: n.marks,
          text: n.text,
        } as unknown as ProseMirrorNode;
        callback(node, n.pos);
      }
    },
  } as unknown as ProseMirrorNode;
}

// ---------------------------------------------------------------------------
// 테스트
// ---------------------------------------------------------------------------

describe("collectMarkRangesByAnnotationId", () => {
  it("지정한 annotationId 를 가진 mark 의 range 를 수집한다", () => {
    const id = "uuid-abc";
    const doc = makeDocStub([
      {
        pos: 2,
        text: "student",
        marks: [makeMark("topLabel", { annotationId: id, text: "S" })],
      },
    ]);

    const ranges = collectMarkRangesByAnnotationId(doc, id);

    expect(ranges).toHaveLength(1);
    const r: MarkRange = first(ranges);
    expect(r.from).toBe(2);
    expect(r.to).toBe(2 + "student".length); // 9
    expect(r.markName).toBe("topLabel");
  });

  it("다른 annotationId 의 mark 는 수집하지 않는다", () => {
    const doc = makeDocStub([
      {
        pos: 2,
        text: "foo",
        marks: [makeMark("highlight", { annotationId: "other-uuid" })],
      },
    ]);

    const ranges = collectMarkRangesByAnnotationId(doc, "target-uuid");
    expect(ranges).toHaveLength(0);
  });

  it("동일 annotationId 를 가진 split 조각을 모두 수집한다", () => {
    const id = "split-uuid";
    // ProseMirror 가 mark 를 텍스트 노드 경계에서 split 한 케이스 시뮬레이션
    const doc = makeDocStub([
      {
        pos: 2,
        text: "am",
        marks: [makeMark("topLabel", { annotationId: id, text: "S" })],
      },
      {
        pos: 4,
        text: " a",
        marks: [makeMark("topLabel", { annotationId: id, text: "S" })],
      },
      {
        pos: 6,
        text: " boy",
        marks: [makeMark("topLabel", { annotationId: id, text: "S" })],
      },
    ]);

    const ranges = collectMarkRangesByAnnotationId(doc, id);
    expect(ranges).toHaveLength(3);
    expect(first(ranges).from).toBe(2);
    expect(ranges[1]?.from).toBe(4);
    expect(ranges[2]?.from).toBe(6);
  });

  it("annotationId 가 없는 mark 는 무시한다", () => {
    const doc = makeDocStub([
      {
        pos: 2,
        text: "test",
        marks: [makeMark("highlight", { color: "#fef08a" })],
      },
    ]);

    const ranges = collectMarkRangesByAnnotationId(doc, "any-uuid");
    expect(ranges).toHaveLength(0);
  });

  it("텍스트 노드가 아닌 노드(isText=false)는 무시한다", () => {
    const id = "uuid-xyz";
    const doc: ProseMirrorNode = {
      descendants(callback: (node: ProseMirrorNode, pos: number) => boolean | undefined) {
        // non-text node
        callback(
          {
            isText: false,
            nodeSize: 1,
            marks: [makeMark("highlight", { annotationId: id })],
          } as unknown as ProseMirrorNode,
          0
        );
      },
    } as unknown as ProseMirrorNode;

    const ranges = collectMarkRangesByAnnotationId(doc, id);
    expect(ranges).toHaveLength(0);
  });
});
