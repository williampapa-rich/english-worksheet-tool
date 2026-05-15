/**
 * F2-e: Stage F2 회귀 spec
 *
 * ADR-0018 Stage F2 — worksheet preview / PDF export 라우트가 server-side
 * Tiptap (`apps/render/`) 경로를 사용한다.
 *
 * 검증 전략:
 *   - F2 이후 기본 preview 라우트 (`/worksheets/{id}/preview`) 는 backend + DB 없이
 *     E2E 테스트 불가 (실 API 호출 필요).
 *   - 따라서 본 spec 은 Stage F1 PoC 라우트 (`/preview/server-tiptap`) 와 동일한
 *     wrap 정합 assertions 를 **일반화 관점에서** 재실행한다.
 *   - F1 spec (wrap_parity_stage_f1.spec.ts) 의 구조 검증을 F2 통합 관점에서 확인.
 *   - 주요 검증: C1/C2/C3 시나리오에서 server-side Tiptap HTML 이 올바른
 *     annotation mark 구조를 출력한다.
 *
 * 주의 (ServerTiptapPreview 경로):
 *   /preview/server-tiptap 는 브라우저에서 generateHTML 경로를 사용한다
 *   (Node.js env 코드를 frontend 에 포함 불가). Decoration.widget 은
 *   포함되지 않음 — Python subprocess (bin.ts ProseMirror View) 경로와 별개.
 *   widget DOM assertions 는 F1 ProseMirror View 테스트에서 담당.
 *
 * C1/C2/C3 정의 (사전 가이드 §2.1):
 *   C1: "eliminating" 다음 줄바꿈
 *   C2: bracket + label wrap
 *   C3: curly bracket "{70 zero-waste stores in Seoul}"
 */

import { expect, test } from "@playwright/test";

// ─── F2-e: C1/C2/C3 annotation mark 구조 검증 ───────────────────────────────

test.describe("F2-e C1 — annotation mark 구조 정합", () => {
  test("C1: top_label mark span 이 HTML 에 포함된다", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C1");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    // top_label mark span (data-annotation-kind)
    const annotSpan = preview.locator("[data-annotation-kind='top_label']").first();
    await expect(annotSpan).toBeVisible();

    // 본문 텍스트 포함
    const text = await preview.textContent();
    expect(text).toContain("eliminating");
  });

  test("C1: top_label text attr (data-top-label-text) 가 존재한다", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C1");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const labelSpan = preview.locator("[data-annotation-kind='top_label']").first();
    await expect(labelSpan).toBeVisible();
    // top_label text attr 확인 — F2 후 동일 attr 유지
    await expect(labelSpan).toHaveAttribute("data-top-label-text", "목적어구");
  });
});

test.describe("F2-e C2 — bracket + label mark 구조 정합", () => {
  test("C2: bracket mark span 이 HTML 에 포함된다", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C2");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    const bracketSpan = preview.locator("[data-bracket-style]");
    await expect(bracketSpan).toBeVisible();
    // bracket style 확인
    await expect(bracketSpan).toHaveAttribute("data-bracket-style", "()");
  });

  test("C2: top_label mark span 이 'seller and buyer' 를 wrap 한다", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C2");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const labelSpan = preview.locator("[data-annotation-kind='top_label']");
    const text = await labelSpan.textContent();
    expect(text).toBe("seller and buyer");
  });
});

test.describe("F2-e C3 — curly bracket mark 구조 정합", () => {
  test("C3: bracket mark span 이 '{}'  style 로 존재한다", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C3");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const bracketSpan = preview.locator("[data-bracket-style='{}']");
    await expect(bracketSpan).toBeVisible();
  });

  test("C3: bracket span 이 '70 zero-waste stores in Seoul' 텍스트를 wrap 한다", async ({
    page,
  }) => {
    await page.goto("/preview/server-tiptap?scenario=C3");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const bracketSpan = preview.locator("[data-bracket-style='{}']");
    const text = await bracketSpan.textContent();
    expect(text).toBe("70 zero-waste stores in Seoul");
  });
});

// ─── F2-e: Zero Waste passage 단락 분리 ──────────────────────────────────────

test.describe("F2-e: Zero Waste — 단락 분리 검증", () => {
  test("zero-waste passage — 7 단락이 7개의 <p> 로 출력된다", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=zero-waste");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    const paragraphs = preview.locator("p");
    const count = await paragraphs.count();
    // Zero Waste passage 는 7 단락 → 7개의 <p> 태그
    expect(count).toBe(7);
  });
});

// ─── F2-e: Python subprocess 출력 구조 검증 (기존 F1 spec 일반화) ─────────────

test.describe("F2-e: annotation mark DOM 구조 — F1 spec 일반화", () => {
  test("data-annotation-kind attr 가 DOM 에 존재한다 (C1)", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C1");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const annotKind = preview.locator("[data-annotation-kind]").first();
    await expect(annotKind).toBeVisible();
  });

  test("data-annotation-kind='top_label' 가 C2 에 존재한다", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C2");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const labelSpan = preview.locator("[data-annotation-kind='top_label']");
    await expect(labelSpan).toBeVisible();
    await expect(labelSpan).toHaveAttribute("data-top-label-text", "주어");
  });

  test("에러 element 가 없다 (C1/C2/C3 모두)", async ({ page }) => {
    for (const scenario of ["C1", "C2", "C3"]) {
      await page.goto(`/preview/server-tiptap?scenario=${scenario}`);
      await page.waitForLoadState("networkidle");

      const errorEl = page.locator("[data-error='true']");
      await expect(errorEl).toHaveCount(0);
    }
  });
});
