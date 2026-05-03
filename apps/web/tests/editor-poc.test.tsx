/**
 * EditorPoc 단위 테스트
 *
 * 검증 항목:
 * 1. 컴포넌트 마운트 성공
 * 2. 초기 텍스트 렌더링 확인
 * 3. "SyntaxAnnotation[] 보기" 버튼 클릭 → JSON 패널 출력
 * 4. JSON 루트 구조 검증 (type: "doc", content 배열)
 *
 * 하이라이트 자동 검증:
 *   jsdom 환경에서 텍스트 선택(Selection API) + 마크 적용이 불안정하므로
 *   하이라이트 적용 자체는 수동 검증으로 대체한다.
 *   (브라우저에서 텍스트 선택 → "하이라이트 토글" 클릭 → JSON에 mark 확인)
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
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
});
