/**
 * preset-and-chip.test.tsx — C-2b 신규 기능 단위 테스트 (vitest + React Testing Library)
 *
 * 검증 항목:
 *   A. SentenceRolePresetBar (AnalysisTable 통해 간접 테스트)
 *     A-1. preset 버튼 5개가 표시된다
 *     A-2. preset 버튼 클릭 시 onSentenceRolePresetClick 콜백 호출
 *     A-3. "+" 버튼 클릭 → 입력 필드 표시 → 입력 후 Enter → onSentenceRolePresetAdd 호출
 *     A-4. "✕" (preset 삭제) 클릭 시 onSentenceRolePresetRemove 호출
 *
 *   B. AnnotationChipView highlight 자유색상 동기화 (PM 결정 1)
 *     B-1. highlightHex 가 있으면 chip 배경에 해당 hex 가 직접 적용된다
 *     B-2. highlightHex 없고 colorIndex 있으면 CSS 변수 --anno-color-N 이 적용된다
 *     B-3. underline kind 는 highlightHex 가 있어도 gray-200 고정
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalysisTable, type AnnotationChip } from "../src/components/AnalysisTable";

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// 헬퍼
// ---------------------------------------------------------------------------

const NOOP = () => {};

function makeChip(overrides: Partial<AnnotationChip> = {}): AnnotationChip {
  return {
    annotationId: "chip-001",
    kind: "highlight",
    category: "note",
    colorIndex: 1,
    labelText: "",
    spanText: "hello",
    ...overrides,
  };
}

function renderTable({
  chips = [] as AnnotationChip[],
  presets = ["S", "V", "O", "OC", "SC"],
  onPresetClick = vi.fn(),
  onPresetAdd = vi.fn(),
  onPresetRemove = vi.fn(),
} = {}) {
  return render(
    <AnalysisTable
      chips={chips}
      onRemove={NOOP}
      onLabelEntry={NOOP}
      sentenceRolePresets={presets}
      onSentenceRolePresetClick={onPresetClick}
      onSentenceRolePresetAdd={onPresetAdd}
      onSentenceRolePresetRemove={onPresetRemove}
    />
  );
}

// ---------------------------------------------------------------------------
// A. SentenceRolePresetBar
// ---------------------------------------------------------------------------

describe("SentenceRolePresetBar — preset 표시", () => {
  it("A-1: 기본 preset 5개 버튼이 분석표 성분 행에 표시된다", () => {
    renderTable({ presets: ["S", "V", "O", "OC", "SC"] });
    // 각 preset 버튼이 DOM 에 있는지 확인
    for (const label of ["S", "V", "O", "OC", "SC"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("A-1b: 빈 preset 목록이면 preset 버튼이 없다", () => {
    renderTable({ presets: [] });
    // S/V/O/OC/SC 버튼 없음 (+ 버튼만 있어야 함)
    expect(screen.queryByRole("button", { name: "S" })).not.toBeInTheDocument();
  });
});

describe("SentenceRolePresetBar — preset 클릭", () => {
  it("A-2: preset 버튼 클릭 시 onSentenceRolePresetClick(label) 호출", () => {
    const onPresetClick = vi.fn();
    renderTable({ onPresetClick });

    fireEvent.click(screen.getByRole("button", { name: "S" }));
    expect(onPresetClick).toHaveBeenCalledWith("S");
  });

  it("A-2b: 다른 preset 버튼도 각자의 label 로 호출된다", () => {
    const onPresetClick = vi.fn();
    renderTable({ onPresetClick });

    fireEvent.click(screen.getByRole("button", { name: "OC" }));
    expect(onPresetClick).toHaveBeenCalledWith("OC");
  });
});

describe("SentenceRolePresetBar — preset 추가", () => {
  it("A-3: '+' 버튼 클릭 후 Enter 입력 시 onSentenceRolePresetAdd 호출", async () => {
    const onPresetAdd = vi.fn();
    renderTable({ onPresetAdd });

    // "+" 버튼 클릭 → input 표시
    const addBtn = screen.getByTitle("커스텀 preset 추가");
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByPlaceholderText("라벨 (최대 16자)")).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText("라벨 (최대 16자)");
    fireEvent.change(input, { target: { value: "Adv" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onPresetAdd).toHaveBeenCalledWith("Adv");
  });

  it("A-3b: Escape 키로 입력 취소 시 콜백 미호출", async () => {
    const onPresetAdd = vi.fn();
    renderTable({ onPresetAdd });

    fireEvent.click(screen.getByTitle("커스텀 preset 추가"));
    await waitFor(() => {
      expect(screen.getByPlaceholderText("라벨 (최대 16자)")).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText("라벨 (최대 16자)");
    fireEvent.change(input, { target: { value: "Adv" } });
    fireEvent.keyDown(input, { key: "Escape" });

    expect(onPresetAdd).not.toHaveBeenCalled();
  });
});

describe("SentenceRolePresetBar — preset 삭제", () => {
  it("A-4: preset 삭제 버튼(✕) 클릭 시 onSentenceRolePresetRemove(label) 호출", () => {
    const onPresetRemove = vi.fn();
    renderTable({ presets: ["S", "V"], onPresetRemove });

    // S 삭제 버튼 클릭 (title = "S preset 삭제")
    const removeBtn = screen.getByTitle("S preset 삭제");
    fireEvent.click(removeBtn);

    expect(onPresetRemove).toHaveBeenCalledWith("S");
  });
});

// ---------------------------------------------------------------------------
// B. highlight 자유색상 chip 동기화
// ---------------------------------------------------------------------------

describe("AnnotationChipView — highlight 자유색상 동기화", () => {
  it("B-1: highlightHex 가 있으면 chip style 에 backgroundColor 로 해당 hex 가 직접 적용된다", () => {
    const chip = makeChip({
      kind: "highlight",
      highlightHex: "#ff6600",
      colorIndex: null,
    });
    renderTable({ chips: [chip], presets: [] });

    // anno-chip 요소를 찾아 style 확인
    const chipEl = screen.getByText("hello").closest(".anno-chip");
    expect(chipEl).toBeTruthy();
    // inline style backgroundColor 에 hex 가 적용되어야 함
    const style = (chipEl as HTMLElement).getAttribute("style") ?? "";
    expect(style).toContain("background-color: rgb(255, 102, 0)");
  });

  it("B-2: highlightHex 없고 colorIndex 있으면 CSS 변수가 배경에 적용된다", () => {
    const chip = makeChip({
      kind: "highlight",
      highlightHex: null,
      colorIndex: 3,
    });
    renderTable({ chips: [chip], presets: [] });

    const chipEl = screen.getByText("hello").closest(".anno-chip");
    expect(chipEl).toBeTruthy();
    const style = (chipEl as HTMLElement).getAttribute("style") ?? "";
    expect(style).toContain("--anno-color-3");
  });

  it("B-3: underline kind 는 highlightHex 가 있어도 gray-200 고정", () => {
    const chip = makeChip({
      kind: "underline",
      category: "note",
      // highlightHex 는 underline 에 의미 없지만 방어적으로 전달
      highlightHex: "#ff0000",
      colorIndex: 1,
    });
    renderTable({ chips: [chip], presets: [] });

    const chipEl = screen.getByText("hello").closest(".anno-chip");
    expect(chipEl).toBeTruthy();
    const style = (chipEl as HTMLElement).getAttribute("style") ?? "";
    // underline 은 gray-200 고정: #e5e7eb
    expect(style).toContain("background-color: rgb(229, 231, 235)");
  });
});
