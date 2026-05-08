/**
 * Stage E3 회귀 — PassageBodyEditor 본문 편집 → annotation 삭제 → 재조회.
 *
 * ADR-0015 Stage E3 DoD 마지막 항목. backend 가 ``patchPassageBody`` 호출 시
 * 동일 트랜잭션에서 ``SyntaxAnnotation.replace_all([])`` 을 실행 — 본문 char
 * offset 무효화 회피. 본 테스트는 그 정책을 시각/계약 단위로 검증.
 *
 * 시나리오:
 *   1. fixture worksheet 로드 → 좌측 "해석 / 어휘 / 본문" 모드 진입.
 *   2. Q1 (Test Passage / William) — annotation 5건 (DB 시드) 가 있는 상태.
 *   3. PassageBodyEditor textarea 에 본문 끝에 'X' 추가 (편집).
 *   4. 저장 버튼 클릭 → confirm 다이얼로그 자동 수락.
 *   5. backend 검증: annotation 0건 + body_text 끝에 'X' 포함.
 *
 * fixture 가 사라지면 skip — 별도 라이프사이클 관리는 후속.
 */
import { expect, test } from "@playwright/test";

const WORKSHEET_ID = "239745e7-e1b1-465c-b614-200e1a005b0f";
const Q1_PASSAGE_ID = "aead6d8a-2097-47a1-9b9d-29dc4a8343ec";
const API_BASE = "http://localhost:8000";

test("본문 수정 → annotation 전부 삭제 → 저장 → 재조회 (Stage E3 DoD)", async ({ page }) => {
  // fixture skip
  const wsResp = await page.request.get(`${API_BASE}/worksheets/${WORKSHEET_ID}`);
  test.skip(wsResp.status() === 404, "fixture worksheet 가 DB 에 없음");
  const passageResp = await page.request.get(`${API_BASE}/passages/${Q1_PASSAGE_ID}`);
  test.skip(passageResp.status() === 404, "fixture passage 가 DB 에 없음");

  // 1. 사전 — annotation 이 *있어야* 의미 있는 검증.
  const annsBefore = await page.request.get(`${API_BASE}/passages/${Q1_PASSAGE_ID}/annotations`);
  const annsBeforeJson = (await annsBefore.json()) as { annotations: unknown[] };
  test.skip(
    annsBeforeJson.annotations.length === 0,
    "fixture passage 에 annotation 이 없음 (시나리오 무의미)"
  );

  // 2. 통합 편집 페이지 진입.
  await page.goto(`/worksheets/${WORKSHEET_ID}/edit`);
  await page.waitForTimeout(2500);

  // Q1 탭 선택 (이미 default 일 수 있음).
  const tabs = page.locator("button", { hasText: /^\d+\./ });
  await tabs.nth(0).click();
  await page.waitForTimeout(500);

  // "해석 / 어휘 / 본문" 모드 (default 이지만 명시 클릭).
  await page.getByRole("button", { name: "해석 / 어휘 / 본문" }).click();
  await page.waitForTimeout(1000);

  // 3. 본문 textarea 에 'X' 추가 — PassageBodyEditor 의 textarea 타겟.
  const textarea = page.getByPlaceholder("영어 본문 (paragraph 는 빈 줄로 분리)");
  const original = (await textarea.inputValue()) ?? "";
  await textarea.fill(`${original}X`);

  // 4. 저장 — confirm 자동 수락.
  page.once("dialog", (dialog) => {
    void dialog.accept();
  });
  await page.getByRole("button", { name: "저장" }).first().click();
  // 저장 완료 대기 — dirty 표시 사라짐 또는 textarea 값 stable.
  await page.waitForTimeout(2500);

  // 5. backend 검증.
  const passageAfter = await page.request.get(`${API_BASE}/passages/${Q1_PASSAGE_ID}`);
  const passageAfterJson = (await passageAfter.json()) as {
    passage: { body_text: string };
  };
  expect(passageAfterJson.passage.body_text.endsWith("X")).toBe(true);

  const annsAfter = await page.request.get(`${API_BASE}/passages/${Q1_PASSAGE_ID}/annotations`);
  const annsAfterJson = (await annsAfter.json()) as { annotations: unknown[] };
  expect(annsAfterJson.annotations.length).toBe(0);
});
