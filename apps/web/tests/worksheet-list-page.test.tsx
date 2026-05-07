/**
 * WorksheetListPage 단위 테스트
 *
 * 검증 항목:
 *   1. 마운트 직후 "불러오는 중…" 표시
 *   2. 빈 목록 응답 → 빈 안내 카드 표시
 *   3. 목록 응답 → 각 worksheet 카드 표시 + /worksheets/:id 링크
 *   4. fetch 실패 → 에러 카드 표시
 *
 * fetch 는 vi.spyOn(global, "fetch") 로 stub.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorksheetListPage } from "../src/pages/WorksheetListPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mockFetchOnce(body: unknown, init?: { ok?: boolean; status?: number }) {
  return vi.spyOn(global, "fetch").mockResolvedValueOnce({
    ok: init?.ok ?? true,
    status: init?.status ?? 200,
    statusText: "OK",
    json: async () => body,
  } as Response);
}

function renderPage() {
  return render(
    <MemoryRouter>
      <WorksheetListPage />
    </MemoryRouter>
  );
}

describe("WorksheetListPage", () => {
  beforeEach(() => {
    // 각 테스트가 자체 mockFetchOnce 호출
  });

  it("마운트 직후 '불러오는 중…' 표시", async () => {
    // fetch 가 pending 상태일 때 검사 — 즉시 mock 하지 않고 지연
    let resolveFetch: ((value: Response) => void) | undefined;
    vi.spyOn(global, "fetch").mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve;
        })
    );
    renderPage();
    expect(screen.getByText("불러오는 중…")).toBeInTheDocument();
    // cleanup 위해 resolve
    resolveFetch?.({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ worksheets: [], total: 0, limit: 100, offset: 0 }),
    } as Response);
  });

  it("빈 목록 응답 → 빈 안내 카드 표시", async () => {
    mockFetchOnce({ worksheets: [], total: 0, limit: 100, offset: 0 });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/아직 학생 자료가 없습니다/)).toBeInTheDocument();
    });
  });

  it("목록 응답 → 각 worksheet 카드 + 링크 표시", async () => {
    mockFetchOnce({
      worksheets: [
        {
          id: "ws-1",
          title: "고2 영어 — Zero-Waste",
          subtitle: "Week 01",
          kind: "student",
          template_id: "playful",
          orientation: "portrait",
          instruction: null,
          branding: { academy_name: "테스트 학원" },
          school: null,
          grade: null,
          exam_date: null,
          time_limit: null,
          items: [],
          created_at: "2026-05-07T10:00:00Z",
          updated_at: "2026-05-07T11:00:00Z",
        },
      ],
      total: 1,
      limit: 100,
      offset: 0,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("고2 영어 — Zero-Waste")).toBeInTheDocument();
    });
    expect(screen.getByText(/Week 01/)).toBeInTheDocument();
    expect(screen.getByText("학생용")).toBeInTheDocument();
    expect(screen.getByText("playful")).toBeInTheDocument();
    expect(screen.getByText("테스트 학원")).toBeInTheDocument();
    // 카드가 /worksheets/:id 링크로 감싸짐
    const link = screen.getByRole("link", { name: /고2 영어/ });
    expect(link).toHaveAttribute("href", "/worksheets/ws-1");
  });

  it("fetch 실패 → 에러 카드 표시", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => ({ detail: "DB 연결 실패" }),
    } as Response);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/목록을 불러오지 못했습니다/)).toBeInTheDocument();
    });
    expect(screen.getByText("DB 연결 실패")).toBeInTheDocument();
  });
});
