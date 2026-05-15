/**
 * visual_regression_annotation.spec.ts — annotation 픽셀 단위 시각 비전 회귀 spec
 *
 * ## 목적
 *
 * 좌표(Y줄번호) 정합 검증(wrap_parity_stage_f3.spec.ts)에서 한 층 더 나아가,
 * annotation 의 *픽셀 단위 시각 렌더링*이 회귀하지 않았는지 자동 감지한다.
 *
 * 이전 와이프 검수(2026-05-15)에서 annotation 시각 미세 회귀("엉망이야 훨씬 나빠졌어")
 * 가 보고된 사례를 바탕으로 도입. 좌표 숫자로는 잡히지 않는 색상/두께/여백 regression
 * 을 스크린샷 diff 로 감지한다.
 *
 * ## 검증 대상 (Zero Waste 지문 기준)
 *
 * - C1: "These supermarkets and grocery stores" 단락 (highlight + underline 동시)
 * - C2: "both seller and buyer work together" 단락 (top_label + bracket 동시)
 * - C3: "Currently, there are more than {70 zero-waste stores in Seoul}" 단락 (bracket 단독)
 * - FULL: zero-waste 전체 7 단락 (paragraph 분리 + padding 시각)
 *
 * ## 환경 고정 전략
 *
 * 비전 회귀 함정 = 폰트 / Chromium 버전 / 디스플레이 scaling 의존성.
 * 대응:
 *   - playwright.config.ts 의 `devices["Desktop Chrome"]` + 1280×720 viewport
 *   - `page.waitForLoadState("networkidle")` → Pretendard CDN 폰트 로드 완료 대기
 *   - 추가 `waitForTimeout(2000)` → 폰트 렌더 안정화
 *   - 스크린샷 영역을 `data-scenario` 속성 locator 로 고정 (절대 좌표 의존 금지)
 *
 * ## 베이스라인
 *
 * 첫 실행 시 `--update-snapshots` 로 생성.
 *   pnpm exec playwright test visual_regression_annotation --update-snapshots
 *
 * 베이스라인 디렉토리:
 *   apps/web/tests/e2e/visual_regression_annotation.spec.ts-snapshots/
 *
 * ## tolerance 설정
 *
 * - `maxDiffPixelRatio: 0.02` — 전체 픽셀의 2% 이내 차이 허용 (폰트 hinting 미세 차이)
 * - `threshold: 0.2` — 개별 픽셀 색상 diff 20% 이내 허용
 * - annotation fix PR #82 이후 상태가 baseline → 픽셀 정합 변경 시 assertion 실패
 *
 * @see docs/visual-regression-guide.md
 * @see apps/web/tests/e2e/wrap_parity_stage_f3.spec.ts (좌표 기반 companion spec)
 * @see packages/template_renderer/templates/_passage_body.css (공용 CSS source-of-truth)
 */

import { expect, test } from "@playwright/test";

// ─── 상수 ─────────────────────────────────────────────────────────────────────

/**
 * toHaveScreenshot tolerance — annotation 픽셀 값 변경 금지 정책
 * (memory: feedback_pdf_annotation_visual.md)
 *
 * 폰트 hinting 미세 차이(subpixel rendering)로 인한 false positive 방지.
 * 0.02 = 전체 픽셀 2% 이내 diff 허용.
 */
const SCREENSHOT_OPTIONS = {
  maxDiffPixelRatio: 0.02,
  threshold: 0.2,
} as const;

/** Pretendard CDN 로드 + 폰트 렌더 안정화 대기 (ms) */
const FONT_SETTLE_MS = 2000;

// ─── 헬퍼 ─────────────────────────────────────────────────────────────────────

/**
 * 시나리오 페이지 로드 후 폰트 안정화 대기.
 * `networkidle` = Pretendard CDN 요청 완료 보장.
 */
async function loadScenario(
  page: Parameters<Parameters<typeof test>[1]>[0]["page"],
  scenario: string
): Promise<void> {
  await page.goto(`/preview/server-tiptap?scenario=${scenario}`);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(FONT_SETTLE_MS);
}

// ─── C1: highlight + underline 동시 ─────────────────────────────────────────

test.describe("C1 — highlight + underline 시각 회귀", () => {
  /**
   * C1 단락 전체 스크린샷.
   *
   * "These supermarkets and grocery stores attempt to prevent waste by eliminating
   *  plastic packages altogether." 단락에 highlight(color_index=2) + underline +
   * top_label 이 동시에 적용된 상태의 픽셀 시각을 고정한다.
   *
   * 시나리오: visual-c1 (ServerTiptapPreview.tsx VISUAL_C1_ANNOTATIONS)
   * 베이스라인: PR #82 annotation fix 5건 적용 후 상태.
   * 회귀 감지: highlight 색상 변경 / underline 두께 변경 / mark 영역 경계 변경 시 실패.
   */
  test("C1: highlight + underline 단락 픽셀 고정", async ({ page }) => {
    await loadScenario(page, "visual-c1");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    await expect(preview).toHaveScreenshot("c1-highlight-underline.png", SCREENSHOT_OPTIONS);
  });

  /**
   * top_label 영역 집중 스크린샷.
   *
   * "prevent waste by eliminating plastic packages altogether" 에 걸린
   * top_label="목적어구" 라벨의 시각 픽셀을 고정.
   *
   * 회귀 감지: 라벨 폰트/색상/위치 변경 시 실패.
   */
  test("C1: top_label '목적어구' 라벨 픽셀 고정", async ({ page }) => {
    await loadScenario(page, "visual-c1");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const labelSpan = preview.locator("[data-annotation-kind='top_label']").first();
    await expect(labelSpan).toBeVisible();

    await expect(labelSpan).toHaveScreenshot("c1-top-label.png", SCREENSHOT_OPTIONS);
  });
});

// ─── C2: top_label + bracket + bottom_label 동시 ─────────────────────────────

test.describe("C2 — top_label + bracket + bottom_label 동시 시각 회귀", () => {
  /**
   * C2 단락 전체 스크린샷.
   *
   * "both seller and buyer work together (to minimize the negative impact
   *  on the environment.)" — 주어 라벨 + 부사절 bracket + 동사 하단 라벨이
   * 동시에 적용된 픽셀 시각을 고정.
   *
   * 시나리오: visual-c2 (ServerTiptapPreview.tsx VISUAL_C2_ANNOTATIONS)
   * 회귀 감지: bracket 스타일 변경 / 라벨 위치 변경 / 두 mark 겹침 처리 변경 시 실패.
   */
  test("C2: top_label + bracket + bottom_label 단락 픽셀 고정", async ({ page }) => {
    await loadScenario(page, "visual-c2");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    await expect(preview).toHaveScreenshot("c2-label-bracket.png", SCREENSHOT_OPTIONS);
  });

  /**
   * bracket span 집중 스크린샷.
   *
   * "()" 스타일 bracket 으로 감싼 "to minimize the negative impact on the environment."
   * 영역의 픽셀 시각을 고정.
   */
  test("C2: '()' bracket span 픽셀 고정", async ({ page }) => {
    await loadScenario(page, "visual-c2");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const bracketSpan = preview.locator("[data-bracket-style='()']");
    await expect(bracketSpan).toBeVisible();

    await expect(bracketSpan).toHaveScreenshot("c2-bracket-paren.png", SCREENSHOT_OPTIONS);
  });
});

// ─── C3: bracket 단독 ────────────────────────────────────────────────────────

test.describe("C3 — bracket 단독 시각 회귀", () => {
  /**
   * C3 단락 전체 스크린샷.
   *
   * "Currently, there are more than {70 zero-waste stores in Seoul}." —
   * "{}" curly bracket 단독 적용 픽셀 시각 고정.
   *
   * 회귀 감지: bracket 기호 스타일 / 폰트 크기 / 색상 변경 시 실패.
   */
  test("C3: curly bracket 단락 픽셀 고정", async ({ page }) => {
    await loadScenario(page, "C3");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    await expect(preview).toHaveScreenshot("c3-bracket-curly.png", SCREENSHOT_OPTIONS);
  });

  /**
   * "{}" bracket span 집중 스크린샷.
   *
   * "70 zero-waste stores in Seoul" 텍스트만 감싼 span 의 픽셀 시각 고정.
   */
  test("C3: '{}' bracket span 픽셀 고정", async ({ page }) => {
    await loadScenario(page, "C3");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const bracketSpan = preview.locator("[data-bracket-style='{}']");
    await expect(bracketSpan).toBeVisible();

    await expect(bracketSpan).toHaveScreenshot("c3-bracket-curly-span.png", SCREENSHOT_OPTIONS);
  });
});

// ─── FULL: zero-waste 전체 7 단락 ─────────────────────────────────────────────

test.describe("FULL — zero-waste 전체 단락 시각 회귀", () => {
  /**
   * 전체 7 단락 스크린샷.
   *
   * Zero Waste 지문 7 단락 전체의 픽셀 시각을 고정.
   *
   * 회귀 감지:
   *   - paragraph 분리 여백 변경
   *   - paragraph 경계 padding 변경
   *   - 전체 line-height 변경
   *   - 폰트 크기 / 패밀리 변경
   *
   * annotation fix 정책(memory: feedback_pdf_annotation_visual.md):
   *   - line-height / borderline / 라벨 픽셀 값은 절대 변경 금지.
   *   - 본 스크린샷이 해당 값들을 픽셀 단위로 고정하는 자동 안전망.
   */
  test("FULL: 전체 7 단락 픽셀 고정 (paragraph 분리 + padding 시각)", async ({ page }) => {
    await loadScenario(page, "zero-waste");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    // 7 단락 모두 렌더된 후 스크린샷 (단락 수 확인 → 안정화 보장)
    const paragraphs = preview.locator("p");
    await expect(paragraphs).toHaveCount(7);

    await expect(preview).toHaveScreenshot("full-zero-waste-7paragraphs.png", SCREENSHOT_OPTIONS);
  });

  /**
   * 2번째 단락 (C1 내용 단락) 집중 스크린샷.
   *
   * "These supermarkets and grocery stores..." — 전체 passage 컨텍스트 안에서
   * 2번째 단락의 픽셀 시각 고정. 단일 단락 C1 spec 과 컨텍스트가 달라 보완 역할.
   */
  test("FULL: 2번째 단락 (These supermarkets) 픽셀 고정", async ({ page }) => {
    await loadScenario(page, "zero-waste");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    // zero-waste 시나리오에서는 annotations 가 없으므로 2번째 <p> 를 직접 캡처
    const secondParagraph = preview.locator("p").nth(1);
    await expect(secondParagraph).toBeVisible();

    await expect(secondParagraph).toHaveScreenshot(
      "full-second-paragraph.png",
      SCREENSHOT_OPTIONS
    );
  });
});
