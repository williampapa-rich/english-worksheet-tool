/**
 * EditorPoc 단위 테스트
 *
 * 검증 항목:
 * 1. 컴포넌트 마운트 성공
 * 2. 초기 텍스트 렌더링 확인
 * 3. "SyntaxAnnotation[] 보기" 버튼 클릭 → JSON 패널 출력
 * 4. JSON 루트 구조 검증 (type: "doc", content 배열)
 * 5. PDF 버튼 노출 조건 — fixture 모드(passageId 없음) 에서는 숨김, API 모드에서 표시
 * 6. HWPX 다운로드 버튼 숨김 확인 (ADR-0008 deprecate 처리)
 *
 * 하이라이트 자동 검증:
 *   jsdom 환경에서 텍스트 선택(Selection API) + 마크 적용이 불안정하므로
 *   하이라이트 적용 자체는 수동 검증으로 대체한다.
 *   (브라우저에서 텍스트 선택 → "하이라이트 토글" 클릭 → JSON에 mark 확인)
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EditorPoc } from "../src/pages/EditorPoc";

// 각 테스트 후 DOM 정리
afterEach(() => {
  cleanup();
});

function renderEditorPoc() {
  return render(
    <MemoryRouter>
      <EditorPoc />
    </MemoryRouter>
  );
}

describe("EditorPoc", () => {
  it("컴포넌트가 정상적으로 마운트된다", () => {
    renderEditorPoc();
    expect(screen.getByText("구문분석 에디터 드래프트 (P1-2c)")).toBeInTheDocument();
  });

  it("초기 텍스트(예시 문장)가 에디터에 렌더링된다", async () => {
    renderEditorPoc();
    // Tiptap이 비동기로 초기화되므로 waitFor 사용
    await waitFor(() => {
      expect(screen.getByText(/The student who had studied hard/)).toBeInTheDocument();
    });
  });

  it('"SyntaxAnnotation[] 보기" 버튼 클릭 시 JSON 패널이 표시된다', async () => {
    renderEditorPoc();

    // Tiptap 초기화 대기
    await waitFor(() => {
      expect(screen.getByText(/The student who had studied hard/)).toBeInTheDocument();
    });

    const jsonButton = screen.getByRole("button", { name: "SyntaxAnnotation[] 보기" });
    fireEvent.click(jsonButton);

    await waitFor(() => {
      const preEl = screen.getByTestId("serialized-annotations");
      expect(preEl).toBeInTheDocument();
    });
  });

  it("직렬화된 JSON 이 SerializedAnnotation[] 배열 형식이다", async () => {
    renderEditorPoc();

    await waitFor(() => {
      expect(screen.getByText(/The student who had studied hard/)).toBeInTheDocument();
    });

    const jsonButton = screen.getByRole("button", { name: "SyntaxAnnotation[] 보기" });
    fireEvent.click(jsonButton);

    await waitFor(() => {
      const preEl = screen.getByTestId("serialized-annotations");
      const parsed = JSON.parse(preEl.textContent ?? "[]");
      // P1-2b 이후 직렬화 결과는 SerializedAnnotation[] (annotation 없으면 빈 배열)
      expect(Array.isArray(parsed)).toBe(true);
    });
  });

  it('"홈으로" 링크가 존재한다', () => {
    renderEditorPoc();
    const homeLink = screen.getByRole("link", { name: /홈으로/ });
    expect(homeLink).toHaveAttribute("href", "/");
  });

  it("fixture 모드(passageId 없음)에서 PDF 다운로드 버튼이 표시되지 않는다", async () => {
    // fixture 모드: URL에 passageId 없음 → isLoadMode = false → PDF / 저장 버튼 숨김
    renderEditorPoc();
    await waitFor(() => {
      expect(screen.getByText(/The student who had studied hard/)).toBeInTheDocument();
    });
    // PDF 버튼은 API 로드 모드 전용 — fixture 모드에서는 존재하지 않아야 함
    expect(screen.queryByTestId("pdf-download-btn")).not.toBeInTheDocument();
  });

  it("HWPX 다운로드 버튼이 존재하지 않는다 (ADR-0008 deprecate 처리)", async () => {
    // ADR-0008 §5 채택안 A: HWPX 다운로드 버튼 숨김 (옵션 A)
    renderEditorPoc();
    await waitFor(() => {
      expect(screen.getByText(/The student who had studied hard/)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "HWPX 다운로드" })).not.toBeInTheDocument();
  });

  it("API 모드(passageId 있음)에서 PDF 다운로드 버튼이 표시된다", async () => {
    // API 로드 모드: URL에 passageId 있음 → isLoadMode = true → PDF 버튼 표시
    // fetch mock — getPassage / getAnnotations 가 실패하지 않도록 stub
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/annotations")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ annotations: [] }),
          });
        }
        // getPassage
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              passage: {
                id: "test-p1",
                body_text: "Hello world.",
                paragraphs: ["Hello world."],
              },
              questions: [],
            }),
        });
      })
    );

    render(
      <MemoryRouter initialEntries={["/editor/test-p1"]}>
        <Routes>
          <Route path="/editor/:passageId" element={<EditorPoc />} />
        </Routes>
      </MemoryRouter>
    );

    // 로딩 완료 대기
    await waitFor(
      () => {
        expect(screen.queryByText("로딩 중...")).not.toBeInTheDocument();
      },
      { timeout: 5000 }
    );

    // PDF 버튼이 렌더되어야 함
    await waitFor(() => {
      expect(screen.getByTestId("pdf-download-btn")).toBeInTheDocument();
    });

    vi.unstubAllGlobals();
  });
});
