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
 *
 * 비전 회귀 (visual_regression_annotation.spec.ts):
 *   - viewport 1280×720 고정 → 환경별 스크린샷 크기 일관성
 *   - `devices["Desktop Chrome"]` 고정 → DPR / UA 일관성
 *   - 스냅샷 디렉토리: tests/e2e/visual_regression_annotation.spec.ts-snapshots/
 *   - 베이스라인 생성: pnpm exec playwright test visual_regression_annotation --update-snapshots
 *   - CI/local 환경 차이: docs/visual-regression-guide.md 참조
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",

  /* 전역 타임아웃
   * 비전 spec 은 폰트 CDN 로드(networkidle) + 2초 안정화 포함 — 30s 유지 */
  timeout: 30_000,
  expect: {
    /* toHaveScreenshot 의 기본 timeout. 비전 diff 계산 포함해 넉넉히. */
    timeout: 15_000,
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
    /* 비전 회귀 환경 고정:
     * - viewport 1280×720: 비전 스크린샷 크기 일관성. widescreen(1920) 은 passage
     *   body 626px 고정이라 실질 차이 없지만 스크린샷 파일 크기 절감 목적.
     * - deviceScaleFactor 1: Retina(2x) Mac 에서 스크린샷 2배 커지는 함정 방지.
     *   Retina 에서 생성한 baseline 을 CI(Linux 1x) 에서 비교하면 크기 불일치로
     *   항상 실패한다. 1로 고정하면 양쪽 동일 픽셀 크기. */
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  },

  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        /* devices["Desktop Chrome"] 의 viewport/DPR 를 위의 전역 설정으로 override.
         * "Desktop Chrome" 기본 viewport = 1280×720, DPR = 1 — 동일하므로 명시적
         * override 없어도 되지만 문서화 목적으로 유지. */
        viewport: { width: 1280, height: 720 },
        deviceScaleFactor: 1,
      },
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
