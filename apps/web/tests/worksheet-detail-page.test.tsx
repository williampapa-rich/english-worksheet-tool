/**
 * WorksheetDetailPage 단위 테스트 (E2-3a 골격).
 *
 * 검증 항목:
 *   1. 마운트 → 로딩 → 메타 카드 표시.
 *   2. items 렌더 (passage_id link / order / 옵션 토글).
 *   3. PDF 다운로드 버튼 클릭 → POST /worksheets/{id}/export.pdf 호출.
 *   4. fetch 실패 → 에러 카드.
 *
 * iframe / URL.createObjectURL 등 jsdom 한계는 mock 으로 우회.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorksheetDetailPage } from "../src/pages/WorksheetDetailPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  // jsdom: URL.createObjectURL stub
  if (!global.URL.createObjectURL) {
    Object.defineProperty(global.URL, "createObjectURL", {
      value: vi.fn(() => "blob:test"),
      writable: true,
    });
  }
  if (!global.URL.revokeObjectURL) {
    Object.defineProperty(global.URL, "revokeObjectURL", {
      value: vi.fn(),
      writable: true,
    });
  }
});

const MOCK_WS = {
  id: "ws-1",
  title: "고2 영어 — Zero-Waste",
  subtitle: "Week 01",
  kind: "student" as const,
  template_id: "playful",
  orientation: "portrait" as const,
  instruction: null,
  branding: { academy_name: "테스트 학원" },
  school: null,
  grade: null,
  exam_date: null,
  time_limit: null,
  items: [
    {
      id: "item-1",
      passage_id: "passage-1234-aaaa-aaaa-aaaaaaaaaaaa",
      order: 0,
      label: null,
      include_translation: true,
      include_vocabulary: true,
      include_syntax_annotations: false,
      include_questions: false,
      include_variants: false,
    },
  ],
  created_at: "2026-05-07T10:00:00Z",
  updated_at: "2026-05-07T11:00:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/worksheets/ws-1"]}>
      <Routes>
        <Route path="/worksheets/:id" element={<WorksheetDetailPage />} />
        <Route path="/editor/:passageId" element={<div data-testid="editor">에디터</div>} />
      </Routes>
    </MemoryRouter>
  );
}

function mockJson(body: unknown, init?: { ok?: boolean; status?: number }) {
  return {
    ok: init?.ok ?? true,
    status: init?.status ?? 200,
    statusText: "OK",
    json: async () => body,
    blob: async () => new Blob(["%PDF"], { type: "application/pdf" }),
    headers: new Headers({
      "content-disposition": "attachment; filename*=UTF-8''ws.pdf",
    }),
  } as unknown as Response;
}

describe("WorksheetDetailPage", () => {
  it("로딩 → 메타 카드 + items 표시", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(mockJson(MOCK_WS));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("고2 영어 — Zero-Waste")).toBeInTheDocument();
    });
    expect(screen.getByText(/테스트 학원/)).toBeInTheDocument();
    expect(screen.getByText(/학생용/)).toBeInTheDocument();
    expect(screen.getByText(/playful/)).toBeInTheDocument();
    expect(screen.getByText(/구성 \(1 개 지문\)/)).toBeInTheDocument();
    // passage 링크 — UUID 8자리 prefix + …
    const passageLink = screen.getByRole("link", { name: /passage-/ });
    const expectedPassageId = MOCK_WS.items[0]?.passage_id ?? "";
    expect(passageLink).toHaveAttribute("href", `/editor/${expectedPassageId}`);
    // 옵션 토글 표시
    expect(screen.getByText("·해석")).toBeInTheDocument();
    expect(screen.getByText("·어휘")).toBeInTheDocument();
  });

  it("PDF 다운로드 버튼 → POST /export.pdf 호출", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    fetchSpy.mockResolvedValueOnce(mockJson(MOCK_WS));
    fetchSpy.mockResolvedValueOnce(mockJson(null));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("고2 영어 — Zero-Waste")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /PDF 다운로드/ }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });
    const exportCall = fetchSpy.mock.calls[1];
    expect(String(exportCall?.[0])).toContain("/worksheets/ws-1/export.pdf");
    expect(exportCall?.[1]?.method).toBe("POST");
  });

  it("fetch 실패 → 에러 카드", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      mockJson({ detail: "not found" }, { ok: false, status: 404 })
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/오류가 발생했습니다/)).toBeInTheDocument();
    });
    expect(screen.getByText("not found")).toBeInTheDocument();
  });
});
