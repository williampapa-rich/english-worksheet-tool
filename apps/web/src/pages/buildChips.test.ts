/**
 * buildChips 단위 테스트 (vitest)
 *
 * KIND_PRIORITY dedup 로직:
 *   - 같은 annotationId 의 mark 가 여러 개일 때 우선순위 높은 kind 가 칩 대표가 됨
 *   - top_label > bottom_label > inline_note > bracket > arrow > underline > highlight
 *   - bracket mark 가 top_label 과 annotationId 를 공유할 때 → 칩 1개 (top_label 대표),
 *     bracketStyle 필드는 유지됨
 */

import { describe, expect, it } from "vitest";
import { KIND_PRIORITY, kindPriority } from "./buildChips";

// ---------------------------------------------------------------------------
// kindPriority 단위 테스트
// ---------------------------------------------------------------------------

describe("kindPriority", () => {
  it("top_label 은 가장 높은 우선순위 (0)", () => {
    expect(kindPriority("top_label")).toBe(0);
  });

  it("highlight 은 가장 낮은 명시 우선순위 (6)", () => {
    expect(kindPriority("highlight")).toBe(6);
  });

  it("top_label 우선순위 < bottom_label 우선순위", () => {
    expect(kindPriority("top_label")).toBeLessThan(kindPriority("bottom_label"));
  });

  it("bottom_label 우선순위 < inline_note 우선순위", () => {
    expect(kindPriority("bottom_label")).toBeLessThan(kindPriority("inline_note"));
  });

  it("inline_note 우선순위 < bracket 우선순위", () => {
    expect(kindPriority("inline_note")).toBeLessThan(kindPriority("bracket"));
  });

  it("bracket 우선순위 < arrow 우선순위", () => {
    expect(kindPriority("bracket")).toBeLessThan(kindPriority("arrow"));
  });

  it("arrow 우선순위 < underline 우선순위", () => {
    expect(kindPriority("arrow")).toBeLessThan(kindPriority("underline"));
  });

  it("underline 우선순위 < highlight 우선순위", () => {
    expect(kindPriority("underline")).toBeLessThan(kindPriority("highlight"));
  });

  it("알 수 없는 kind 는 99 (가장 낮음)", () => {
    expect(kindPriority("unknown_kind")).toBe(99);
  });
});

// ---------------------------------------------------------------------------
// KIND_PRIORITY 상수 완전성 검증
// ---------------------------------------------------------------------------

describe("KIND_PRIORITY", () => {
  it("7가지 kind 가 모두 정의됨", () => {
    const expectedKinds = [
      "top_label",
      "bottom_label",
      "inline_note",
      "bracket",
      "arrow",
      "underline",
      "highlight",
    ];
    for (const kind of expectedKinds) {
      expect(KIND_PRIORITY).toHaveProperty(kind);
    }
  });

  it("우선순위 값이 모두 다름 (중복 없음)", () => {
    const values = Object.values(KIND_PRIORITY);
    const unique = new Set(values);
    expect(unique.size).toBe(values.length);
  });

  it("top_label 이 가장 낮은 숫자 (가장 높은 우선순위)", () => {
    const minValue = Math.min(...Object.values(KIND_PRIORITY));
    expect(KIND_PRIORITY.top_label).toBe(minValue);
  });

  it("highlight 이 가장 높은 숫자 (가장 낮은 우선순위)", () => {
    const maxValue = Math.max(...Object.values(KIND_PRIORITY));
    expect(KIND_PRIORITY.highlight).toBe(maxValue);
  });
});
