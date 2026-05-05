/**
 * editor-roundtrip.spec.ts — P1-6b Playwright E2E 골격 시나리오
 *
 * 시나리오: passage 로드 → 형광펜 적용 → 저장 → PDF 다운로드 버튼 표시 확인
 *
 * P1-10e 변경 (ADR-0008 §5 채택안 A):
 *   - HWPX 다운로드 단계 → PDF 다운로드 단계로 교체.
 *   - PDF 다운로드는 window.print() (print 다이얼로그) 로 처리 — 실제 다운로드 파일 없음.
 *     따라서 download 이벤트 대신 버튼이 노출되는지 + 클릭 후 토스트 확인으로 검증.
 *   - window.print() Playwright 에서 dialog 이벤트 발생 없음 (headless 는 print 다이얼로그 skip).
 *     검증 전략: PDF 버튼이 DOM 에 존재하는지 + 클릭 후 저장 완료 토스트 확인.
 *
 * 전략:
 *   - FastAPI/DB 미기동. setupApiMocks() 로 backend 호출을 정적 fixture 로 대체.
 *   - ProseMirror selection: 키보드 입력 단일 경로.
 *     Playwright keyboard 이벤트는 contenteditable 의 ProseMirror plugin 으로
 *     직접 흘러가 ProseMirror state 의 selection 으로 잡힌다.
 *     browser-level Selection / blur / focus 다툼을 회피.
 */

import { expect, test } from "@playwright/test";
import { setupApiMocks } from "./api-mock";

const PASSAGE_ID = "test-passage-1";
const BODY_TEXT = "The student who had studied hard for the exam passed with an excellent score.";

test("passage 로드 → 형광펜 적용 → 저장 → PDF 다운로드 버튼 확인", async ({ page }) => {
  // ── 1. API mock 등록 ─────────────────────────────────────────────────────
  await setupApiMocks(page, { passageId: PASSAGE_ID, bodyText: BODY_TEXT });

  // ── 2. 에디터 페이지 진입 (API 로드 모드) ───────────────────────────────
  await page.goto(`/editor/${PASSAGE_ID}`);

  // 로딩 스피너가 사라지고 본문이 렌더될 때까지 대기
  await expect(page.locator(".ProseMirror p").first()).toContainText("The student", {
    timeout: 15_000,
  });

  // ── 3. 본문 일부 선택 (키보드로 첫 N글자) ─────────────────────────────────
  //
  // ProseMirror state 에 selection 을 박는 가장 안정적인 방법은 키보드 입력.
  // Playwright keyboard 이벤트는 contenteditable 의 ProseMirror plugin 으로
  // 직접 흘러가 ProseMirror state 의 selection 으로 잡힌다.
  // browser-level Selection / blur / focus 다툼을 회피.
  const proseMirror = page.locator(".ProseMirror");
  await proseMirror.click({ position: { x: 50, y: 20 } });

  // OS 별 modifier 분기 — macOS 는 Meta, 그 외는 Control
  const isMac = process.platform === "darwin";
  const homeShortcut = isMac ? "Meta+ArrowUp" : "Control+Home";

  // 문서 시작으로 이동 후 첫 3글자 ("The") 선택
  await page.keyboard.press(homeShortcut);
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press("Shift+ArrowRight");
  }

  // selection 이 ProseMirror state 에 잡혔는지 확인 (browser Selection API 기준)
  await page.waitForFunction(
    () => {
      const sel = window.getSelection();
      return sel !== null && sel.toString().trim().length > 0;
    },
    { timeout: 3_000 }
  );

  // ── 4. 형광펜 버튼 클릭 ─────────────────────────────────────────────────
  const highlightBtn = page.getByRole("button", { name: "형광펜" });
  await highlightBtn.click();

  // mark 가 적용되어야 한다 — silent fail 금지. 회귀 방지의 핵심 검증.
  // HighlightMark 는 @tiptap/extension-highlight 기반으로 <mark style="..."> 로 렌더.
  // (renderHTML: ['mark', HTMLAttributes, 0] — tiptap extension-highlight v2 확인됨)
  const highlightSpan = proseMirror.locator("mark[style]");
  await expect(highlightSpan).toHaveCount(1, { timeout: 3_000 });

  // ── 5. 저장 버튼 클릭 → 토스트 확인 ──────────────────────────────────
  const saveBtn = page.getByRole("button", { name: "저장" });
  await saveBtn.click();

  // "저장 완료" 토스트 (output[aria-live="polite"]) 가 5초 내 나타나야 함
  await expect(page.getByText("저장 완료")).toBeVisible({ timeout: 8_000 });

  // ── 6. PDF 다운로드 버튼 확인 (ADR-0008 §5 채택안 A) ──────────────────
  //
  // PDF 다운로드는 window.print() 로 print 다이얼로그 트리거 — headless 환경에서
  // 실제 download 이벤트 없음. 버튼 존재 + 클릭 후 토스트 확인으로 검증.
  // HWPX 다운로드 버튼은 ADR-0008 deprecate 결정으로 숨김 처리됨 — 존재 확인 X.
  const pdfBtn = page.getByTestId("pdf-download-btn");
  await expect(pdfBtn).toBeVisible({ timeout: 3_000 });
  await expect(pdfBtn).toBeEnabled();

  // HWPX 다운로드 버튼은 숨김 처리 (ADR-0008 §5 HWPX deprecate)
  const hwpxBtn = page.getByRole("button", { name: "HWPX 다운로드" });
  await expect(hwpxBtn).toHaveCount(0);

  // PDF 버튼 클릭 → 저장 후 토스트 확인
  // window.print() 는 headless Chrome 에서 no-op (다이얼로그 없음) — 저장 완료 토스트만 확인.
  await pdfBtn.click();
  await expect(
    page.getByText("인쇄 다이얼로그에서 'PDF 로 저장'을 선택하세요")
  ).toBeVisible({ timeout: 8_000 });
});
