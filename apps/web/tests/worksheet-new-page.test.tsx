/**
 * WorksheetNewPage 단위 테스트
 *
 * 검증 항목:
 *   1. 마운트 → 폼 필드 표시.
 *   2. 제출 → POST /passages/extract → POST /worksheets/ → navigate.
 *   3. 빈 입력 → 클라이언트 검증 에러.
 *   4. fetch 실패 → 에러 카드 + 입력 보존.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorksheetNewPage } from "../src/pages/WorksheetNewPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/worksheets/new"]}>
      <Routes>
        <Route path="/worksheets/new" element={<WorksheetNewPage />} />
        <Route path="/worksheets/:id" element={<div data-testid="ws-detail">상세</div>} />
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
  } as Response;
}

describe("WorksheetNewPage", () => {
  it("마운트 → 폼 필드 표시", () => {
    renderPage();
    expect(screen.getByLabelText("제목")).toBeInTheDocument();
    expect(screen.getByLabelText("영어 지문")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "생성하기" })).toBeInTheDocument();
  });

  it("정상 제출 → extract → createWorksheet → navigate", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    fetchSpy.mockResolvedValueOnce(
      mockJson({
        results: [{ passage: { id: "p-1", body_text: "x" } }],
      })
    );
    fetchSpy.mockResolvedValueOnce(
      mockJson({
        id: "ws-1",
        title: "T",
        subtitle: null,
        kind: "student",
        template_id: "playful",
        orientation: "portrait",
        instruction: null,
        branding: {},
        school: null,
        grade: null,
        exam_date: null,
        time_limit: null,
        items: [],
        created_at: "",
        updated_at: "",
      })
    );

    renderPage();

    fireEvent.change(screen.getByLabelText("제목"), { target: { value: "T" } });
    fireEvent.change(screen.getByLabelText("영어 지문"), {
      target: { value: "Some english body." },
    });
    fireEvent.click(screen.getByRole("button", { name: "생성하기" }));

    await waitFor(() => {
      expect(screen.getByTestId("ws-detail")).toBeInTheDocument();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    const extractCall = fetchSpy.mock.calls[0];
    const wsCall = fetchSpy.mock.calls[1];
    expect(extractCall).toBeDefined();
    expect(wsCall).toBeDefined();
    expect(String(extractCall?.[0])).toContain("/passages/extract");
    expect(extractCall?.[1]?.method).toBe("POST");
    expect(String(wsCall?.[0])).toContain("/worksheets/");
    expect(wsCall?.[1]?.method).toBe("POST");
    const wsBody = JSON.parse(wsCall?.[1]?.body as string);
    expect(wsBody.title).toBe("T");
    expect(wsBody.kind).toBe("student");
    expect(wsBody.template_id).toBe("playful");
    expect(wsBody.items[0].passage_id).toBe("p-1");
  });

  it("빈 입력 → 클라이언트 검증 에러 (fetch 호출 안 됨)", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    renderPage();
    // HTMLFormElement.requestSubmit 우회 — submit 버튼 직접 클릭하면 required 가 막음.
    // 대신 비동기 setError 검사를 위해 폼 자체를 직접 submit.
    const form = screen.getByRole("button", { name: "생성하기" }).closest("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);
    await waitFor(() => {
      expect(screen.getByText(/지문과 제목을 모두 입력해주세요/)).toBeInTheDocument();
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("extract 실패 → 에러 카드 표시", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      mockJson({ detail: "ANTHROPIC_API_KEY missing" }, { ok: false, status: 500 })
    );
    renderPage();
    fireEvent.change(screen.getByLabelText("제목"), { target: { value: "T" } });
    fireEvent.change(screen.getByLabelText("영어 지문"), {
      target: { value: "x" },
    });
    fireEvent.click(screen.getByRole("button", { name: "생성하기" }));

    await waitFor(() => {
      expect(screen.getByText(/생성하지 못했습니다/)).toBeInTheDocument();
    });
    expect(screen.getByText(/ANTHROPIC_API_KEY missing/)).toBeInTheDocument();
    // 입력 값 보존
    expect(screen.getByLabelText("제목")).toHaveValue("T");
  });
});
