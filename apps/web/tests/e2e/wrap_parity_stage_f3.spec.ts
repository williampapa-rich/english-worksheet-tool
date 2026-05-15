/**
 * F3-a: Stage F3 회귀 spec — wrap 위치 Y좌표 정합 (정식 assertion 강화)
 *
 * ADR-0018 Stage F3 산출물.
 *
 * F1/F2 의 ad-hoc 구조 검증(mark DOM 존재 여부)에서 *실질 wrap 위치 정합* 으로 격상.
 * 두 렌더러(에디터 Tiptap ↔ server-side Tiptap generateHTML)의 텍스트 wrap 위치를
 * line-height tolerance 이내로 검증한다.
 *
 * ## 설계 원칙
 *
 * - **동일 뷰포트 내 iframe 측정** 전략 사용 금지 (두 페이지 동시 로드 시 뷰포트 분리).
 *   대신 **상대 줄 번호 비교** 방식 채택:
 *   - 에디터 페이지에서 타겟 단어의 줄 번호(0-indexed) 를 측정.
 *   - server-side preview 페이지에서 타겟 단어의 줄 번호를 측정.
 *   - 줄 번호가 동일하면 wrap 위치 정합.
 *
 * - **line-height tolerance**: 동일 컨테이너 너비(626px) + 동일 폰트(Pretendard)
 *   가정 하에 줄 번호 차이 ≤ 0 (완전 일치)이어야 한다.
 *   단, 두 뷰포트 절대 Y는 다를 수 있으므로 줄 번호(상대값)로 비교.
 *
 * ## 검증 시나리오
 *
 * - C1: "eliminating" 이 첫 줄 끝에 위치 (wrap 위치 → 두 렌더러 동일)
 * - C2: "together" Y 줄 번호 정합 (bracket + label 이 있어도 wrap 불변)
 * - C3: "Currently" 가 단일 줄 — 단 줄 (줄 번호 = 0) 확인
 *
 * ## 호환성 보장 (feedback_pdf_annotation_visual.md)
 *
 * PR #82 에서 고정된 annotation 영역 fix 5건:
 *   - highlight 다중 layer / 12색 정합
 *   - 모서리 굴곡 제거
 *   - 라벨 검정
 *   - paragraph 분리
 * 본 spec 은 이들을 건드리지 않음 — 구조 검증(DOM mark 존재)만 재확인.
 *
 * @see docs/stage-f3-cleanup.md
 */

import { type Locator, expect, test } from "@playwright/test";
import { setupApiMocks } from "./api-mock.js";

// ─── 헬퍼: 단어의 줄 번호(0-indexed) 반환 ────────────────────────────────────

/**
 * 컨테이너 안에서 특정 단어가 몇 번째 줄(0-indexed)에 있는지 반환.
 *
 * 첫 텍스트 노드의 Y를 기준 Y로 잡고, (타겟 Y - 기준 Y) / line-height 로 줄 번호를 계산.
 * line-height 는 computed style에서 읽거나, 없으면 fallback(40px — 12pt/line-height 2.78 기준).
 *
 * 단어를 찾지 못하면 null 반환.
 */
async function getWordLineNumber(locator: Locator, word: string): Promise<number | null> {
  return await locator.evaluate((el: HTMLElement, wordStr: string): number | null => {
    const range = document.createRange();

    // baseline Y (컨테이너 내 첫 텍스트 위치)
    function getFirstTextY(node: Node): number | null {
      if (node.nodeType === Node.TEXT_NODE) {
        const tn = node as Text;
        if (tn.data.trim().length === 0) return null;
        range.setStart(tn, 0);
        range.setEnd(tn, 1);
        const r = range.getBoundingClientRect();
        return r.width > 0 ? r.y : null;
      }
      for (const child of Array.from(node.childNodes)) {
        const y = getFirstTextY(child);
        if (y !== null) return y;
      }
      return null;
    }

    function findWordRect(node: Node): DOMRect | null {
      if (node.nodeType === Node.TEXT_NODE) {
        const tn = node as Text;
        const idx = tn.data.indexOf(wordStr);
        if (idx >= 0) {
          range.setStart(tn, idx);
          range.setEnd(tn, idx + wordStr.length);
          return range.getBoundingClientRect();
        }
      } else {
        for (const child of Array.from(node.childNodes)) {
          const r = findWordRect(child);
          if (r) return r;
        }
      }
      return null;
    }

    const baselineY = getFirstTextY(el);
    if (baselineY === null) return null;

    const wordRect = findWordRect(el);
    if (!wordRect) return null;

    // computed line-height (px). "normal" 이면 폰트 크기 * 1.2 근사.
    const cs = window.getComputedStyle(el);
    const lhStr = cs.lineHeight;
    let lineH = 40; // fallback: 12pt * 2.78 * 96/72 ≈ 44px — 넉넉히 40
    if (lhStr !== "normal" && lhStr !== "") {
      const parsed = Number.parseFloat(lhStr);
      if (!Number.isNaN(parsed) && parsed > 0) lineH = parsed;
    }

    const deltaY = wordRect.y - baselineY;
    return Math.round(deltaY / lineH);
  }, word);
}

/**
 * 컨테이너 안에서 특정 단어의 첫 번째 줄에 있는지 확인 (줄 번호 = 0).
 */
async function isWordOnFirstLine(locator: Locator, word: string): Promise<boolean> {
  const lineNum = await getWordLineNumber(locator, word);
  return lineNum === 0;
}

/**
 * 컨테이너 안에서 특정 단어를 포함하는 텍스트 줄(Y기준)의 텍스트 수집.
 */
async function getFirstLineText(locator: Locator): Promise<string> {
  return await locator.evaluate((el: HTMLElement): string => {
    const range = document.createRange();
    let firstLine = "";
    let firstY: number | null = null;

    function walk(node: Node): boolean {
      if (node.nodeType === Node.TEXT_NODE) {
        const tn = node as Text;
        for (let i = 0; i < tn.length; i++) {
          range.setStart(tn, i);
          range.setEnd(tn, i + 1);
          const r = range.getBoundingClientRect();
          if (r.width === 0) continue;
          if (firstY === null) firstY = Math.round(r.y);
          else if (Math.round(r.y) > firstY + 5) return false;
          firstLine += tn.data[i] ?? "";
        }
      } else {
        for (const child of Array.from(node.childNodes)) {
          if (!walk(child)) return false;
        }
      }
      return true;
    }
    walk(el);
    return firstLine;
  });
}

// ─── Fixture 상수 ─────────────────────────────────────────────────────────────

const PASSAGE_ID_C1 = "c1-test-passage";
const PASSAGE_ID_C2 = "c2-test-passage";
const PASSAGE_ID_C3 = "c3-test-passage";

const C1_BODY =
  "These supermarkets and grocery stores attempt to prevent waste by eliminating plastic packages altogether.";
const C2_BODY =
  "both seller and buyer work together (to minimize the negative impact on the environment.)";
const C3_BODY = "Currently, there are more than {70 zero-waste stores in Seoul}.";

// ─── C1: "eliminating" wrap 위치 정합 ────────────────────────────────────────

test.describe("F3-a C1 — 'eliminating' wrap 줄 번호 정합 [정식 회귀]", () => {
  test("C1: 에디터 첫 줄에 'eliminating' 포함 (서버 렌더 기준)", async ({ page }) => {
    // server-side preview: 단일 단락 — "eliminating" 이 첫 줄에 있어야
    await page.goto("/preview/server-tiptap?scenario=C1");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    const serverFirstLine = await getFirstLineText(preview);
    expect(serverFirstLine).toContain("eliminating");
  });

  test("C1: 에디터 첫 줄 == 서버 렌더 첫 줄 (wrap 정합)", async ({ page }) => {
    // 에디터 측 mock 설정
    await setupApiMocks(page, { passageId: PASSAGE_ID_C1, bodyText: C1_BODY });
    await page.goto(`/editor/${PASSAGE_ID_C1}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    const editor = page.locator(".ProseMirror").first();
    await expect(editor).toBeVisible();
    const editorFirstLine = await getFirstLineText(editor);

    // server-side HTML
    const serverPage = await page.context().newPage();
    await serverPage.goto("/preview/server-tiptap?scenario=C1");
    await serverPage.waitForLoadState("networkidle");
    await serverPage.waitForTimeout(2000);

    const preview = serverPage.locator("[data-server-tiptap-preview='true']");
    const serverFirstLine = await getFirstLineText(preview);
    await serverPage.close();

    // 두 렌더러 첫 줄이 모두 "eliminating" 을 포함해야 (wrap 정합)
    expect(editorFirstLine).toContain("eliminating");
    expect(serverFirstLine).toContain("eliminating");
    // 첫 줄 시작 단어도 동일해야 (모두 "These" 로 시작)
    expect(editorFirstLine).toMatch(/^These/);
    expect(serverFirstLine).toMatch(/^These/);
  });

  test("C1: annotation mark 구조 정합 (top_label DOM 존재)", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C1");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const labelSpan = preview.locator("[data-annotation-kind='top_label']").first();
    await expect(labelSpan).toBeVisible();
    await expect(labelSpan).toHaveAttribute("data-top-label-text", "목적어구");
  });
});

// ─── C2: bracket + label — "together" 줄 번호 정합 ───────────────────────────

test.describe("F3-a C2 — 'together' 줄 번호 정합 [정식 회귀]", () => {
  test("C2: 서버 렌더에서 'together' 가 첫 줄에 있다", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C2");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    // C2 body 는 짧은 단일 단락 — "together" 는 첫 줄에 있어야
    const onFirstLine = await isWordOnFirstLine(preview, "together");
    expect(onFirstLine).toBe(true);
  });

  test("C2: 에디터 vs 서버 렌더 — 'together' 줄 번호 일치", async ({ page }) => {
    await setupApiMocks(page, { passageId: PASSAGE_ID_C2, bodyText: C2_BODY });
    await page.goto(`/editor/${PASSAGE_ID_C2}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    const editor = page.locator(".ProseMirror").first();
    await expect(editor).toBeVisible();
    const editorLineNum = await getWordLineNumber(editor, "together");

    const serverPage = await page.context().newPage();
    await serverPage.goto("/preview/server-tiptap?scenario=C2");
    await serverPage.waitForLoadState("networkidle");
    await serverPage.waitForTimeout(2000);

    const preview = serverPage.locator("[data-server-tiptap-preview='true']");
    const serverLineNum = await getWordLineNumber(preview, "together");
    await serverPage.close();

    // 두 렌더러 모두 "together" 가 null 이 아니어야
    expect(editorLineNum).not.toBeNull();
    expect(serverLineNum).not.toBeNull();

    // 핵심 assertion: 줄 번호가 동일해야 (wrap 위치 정합)
    // C2 는 단일 줄 단락 → 두 렌더러 모두 줄 번호 0
    expect(editorLineNum).toBe(serverLineNum);
  });

  test("C2: bracket mark DOM 구조 — style '()' + 텍스트 wrap 정합", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C2");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const bracketSpan = preview.locator("[data-bracket-style='()']");
    await expect(bracketSpan).toBeVisible();
    const text = await bracketSpan.textContent();
    expect(text).toContain("to minimize");
  });

  test("C2: top_label mark — 'seller and buyer' wrap 정합", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C2");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const labelSpan = preview.locator("[data-annotation-kind='top_label']");
    await expect(labelSpan).toBeVisible();
    await expect(labelSpan).toHaveAttribute("data-top-label-text", "주어");
    const text = await labelSpan.textContent();
    expect(text).toBe("seller and buyer");
  });
});

// ─── C3: curly bracket — "Currently" 단일 줄 ─────────────────────────────────

test.describe("F3-a C3 — 'Currently' 단일 줄 검증 [정식 회귀]", () => {
  test("C3: 서버 렌더에서 'Currently' 가 첫 줄 (단일 줄 단락)", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C3");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    const onFirstLine = await isWordOnFirstLine(preview, "Currently");
    expect(onFirstLine).toBe(true);
  });

  test("C3: 에디터 vs 서버 렌더 — 'Currently' 줄 번호 일치", async ({ page }) => {
    await setupApiMocks(page, { passageId: PASSAGE_ID_C3, bodyText: C3_BODY });
    await page.goto(`/editor/${PASSAGE_ID_C3}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    const editor = page.locator(".ProseMirror").first();
    await expect(editor).toBeVisible();
    const editorLineNum = await getWordLineNumber(editor, "Currently");

    const serverPage = await page.context().newPage();
    await serverPage.goto("/preview/server-tiptap?scenario=C3");
    await serverPage.waitForLoadState("networkidle");
    await serverPage.waitForTimeout(2000);

    const preview = serverPage.locator("[data-server-tiptap-preview='true']");
    const serverLineNum = await getWordLineNumber(preview, "Currently");
    await serverPage.close();

    expect(editorLineNum).not.toBeNull();
    expect(serverLineNum).not.toBeNull();
    // C3 는 짧은 단락 → 첫 줄 (줄 번호 0)
    expect(editorLineNum).toBe(0);
    expect(serverLineNum).toBe(0);
    // 두 렌더러 일치
    expect(editorLineNum).toBe(serverLineNum);
  });

  test("C3: curly bracket span — '70 zero-waste stores in Seoul' 완전 wrap", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C3");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const bracketSpan = preview.locator("[data-bracket-style='{}']");
    await expect(bracketSpan).toBeVisible();
    const text = await bracketSpan.textContent();
    // 정확한 텍스트 wrap 검증
    expect(text).toBe("70 zero-waste stores in Seoul");
  });
});

// ─── F3-a 전역: 에러 없음 + annotation_html.py 호환성 회귀 ───────────────────

test.describe("F3-a 전역 — 에러 없음 + 서버 렌더 안전성", () => {
  for (const scenario of ["C1", "C2", "C3", "zero-waste"] as const) {
    test(`${scenario}: [data-error='true'] 없음`, async ({ page }) => {
      await page.goto(`/preview/server-tiptap?scenario=${scenario}`);
      await page.waitForLoadState("networkidle");

      const errorEl = page.locator("[data-error='true']");
      await expect(errorEl).toHaveCount(0);
    });
  }

  test("zero-waste: 7 단락 → 7개 <p> 태그", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=zero-waste");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    await expect(preview).toBeVisible();

    const paragraphs = preview.locator("p");
    const count = await paragraphs.count();
    expect(count).toBe(7);
  });

  test("C1: data-annotation-kind attr 가 DOM 에 존재한다", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C1");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const annotKind = preview.locator("[data-annotation-kind]").first();
    await expect(annotKind).toBeVisible();
  });

  test("C3: data-bracket-style='{}' span 이 올바른 텍스트를 wrap 한다 (회귀)", async ({ page }) => {
    await page.goto("/preview/server-tiptap?scenario=C3");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const bracketSpan = preview.locator("[data-bracket-style='{}']");
    const text = await bracketSpan.textContent();
    expect(text).toBe("70 zero-waste stores in Seoul");
  });

  test("C2: data-top-label-text='주어' span 이 올바른 텍스트를 wrap 한다 (회귀)", async ({
    page,
  }) => {
    await page.goto("/preview/server-tiptap?scenario=C2");
    await page.waitForLoadState("networkidle");

    const preview = page.locator("[data-server-tiptap-preview='true']");
    const labelSpan = preview.locator("[data-annotation-kind='top_label']");
    const text = await labelSpan.textContent();
    expect(text).toBe("seller and buyer");
  });
});
