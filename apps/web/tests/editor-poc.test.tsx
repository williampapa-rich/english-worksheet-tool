/**
 * EditorPoc 단위 테스트
 *
 * 검증 항목:
 * 1. 컴포넌트 마운트 성공
 * 2. 초기 텍스트 렌더링 확인
 * 3. "JSON 보기" 버튼 클릭 → JSON 패널 출력
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
    expect(screen.getByText("Tiptap 구문분석 에디터 PoC")).toBeInTheDocument();
  });

  it("초기 텍스트(예시 문장)가 에디터에 렌더링된다", async () => {
    renderEditorPoc();
    // Tiptap이 비동기로 초기화되므로 waitFor 사용
    await waitFor(() => {
      expect(screen.getByText(/The student who studied hard/)).toBeInTheDocument();
    });
  });

  it('"JSON 보기" 버튼 클릭 시 JSON 패널이 표시된다', async () => {
    renderEditorPoc();

    // Tiptap 초기화 대기
    await waitFor(() => {
      expect(screen.getByText(/The student who studied hard/)).toBeInTheDocument();
    });

    const jsonButton = screen.getByRole("button", { name: "JSON 보기" });
    fireEvent.click(jsonButton);

    await waitFor(() => {
      const preEl = screen.getByTestId("serialized-json");
      expect(preEl).toBeInTheDocument();
    });
  });

  it("직렬화된 JSON이 ProseMirror 문서 구조(type: doc, content 배열)를 포함한다", async () => {
    renderEditorPoc();

    await waitFor(() => {
      expect(screen.getByText(/The student who studied hard/)).toBeInTheDocument();
    });

    const jsonButton = screen.getByRole("button", { name: "JSON 보기" });
    fireEvent.click(jsonButton);

    await waitFor(() => {
      const preEl = screen.getByTestId("serialized-json");
      type PmDoc = { type?: string; content?: unknown[] };
      const parsed = JSON.parse(preEl.textContent ?? "{}") as PmDoc;

      // ProseMirror 문서 루트는 type: "doc"
      expect(parsed.type).toBe("doc");
      // content 배열에 최소 1개 이상의 노드가 있어야 함
      const content = parsed.content ?? [];
      expect(Array.isArray(content)).toBe(true);
      expect(content.length).toBeGreaterThan(0);
    });
  });

  it('"홈으로" 링크가 존재한다', () => {
    renderEditorPoc();
    const homeLink = screen.getByRole("link", { name: /홈으로/ });
    expect(homeLink).toHaveAttribute("href", "/");
  });
});
