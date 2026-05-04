/**
 * playwright.config.ts — P1-6b Playwright E2E 골격
 *
 * 전략:
 *   - backend (FastAPI/DB) 미기동. page.route() 로 API 응답을 정적 fixture 로 대체.
 *   - 이유: E2E 인프라 baseline 이 목적. backend round-trip 검증은 P1-6a integration
 *     테스트에서 이미 다룸. Playwright 의 가치는 UI 회귀 감지 — 인프라 도입이 핵심.
 *
 * 대안 검토:
 *   - Cypress: Playwright 대비 다운로드 이벤트 처리가 불안정, Tiptap contenteditable
 *     조작 안정성 낮음. Playwright 의 download 이벤트 API 가 더 명시적.
 *   - 직접 구현(없음): E2E 테스트 프레임워크를 직접 만드는 것은 No Reinventing the Wheel
 *     원칙 위반. Playwright 는 Microsoft 검증 오픈소스 표준.
 *
 * 브라우저: chromium 1개 (Phase 1 baseline). Firefox/WebKit 은 회귀 우선순위 낮음.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",

  /* 전역 타임아웃 */
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },

  /* 실패 시 재시도 (CI 에서만) */
  retries: process.env.CI ? 2 : 0,

  /* CI 에서 병렬 비활성화 */
  workers: process.env.CI ? 1 : undefined,

  /* 리포터 */
  reporter: process.env.CI ? "github" : "list",

  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  /* Vite dev 서버 자동 기동 */
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
