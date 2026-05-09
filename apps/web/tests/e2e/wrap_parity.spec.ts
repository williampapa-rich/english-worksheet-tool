/**
 * 회귀 테스트 — 좌측 에디터 (구문분석) 와 우측 PDF 미리보기의 자동 wrap 위치
 * 가 *동일* 한지 검증.
 *
 * 2026-05-09: 폰트 fallback 차이로 글자 폭이 다른 회귀를 잡기 위해 도입.
 * Pretendard webfont 를 양쪽 모두 명시 로드 (_passage_body.css @import) 하면
 * 둘 다 동일 폰트로 매칭 → wrap 위치 픽셀 단위 일치.
 *
 * 검수 fixture worksheet (Coffee Origins) 가 살아있어야 한다.
 * DB seed 가 사라지면 본 테스트 skip — 별도 fixture 라이프사이클 관리는 후속.
 */
import { type Locator, expect, test } from "@playwright/test";

const WORKSHEET_ID = "239745e7-e1b1-465c-b614-200e1a005b0f";

async function getFirstLineText(loc: Locator): Promise<string> {
  return await loc.evaluate((el: HTMLElement) => {
    const p = el.querySelector("p");
    if (!p) return "";
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
          if (firstY === null) firstY = Math.round(r.y);
          else if (Math.round(r.y) > firstY + 5) return false;
          firstLine += tn.data[i];
        }
      } else {
        for (const c of Array.from(node.childNodes)) {
          if (!walk(c)) return false;
        }
      }
      return true;
    }
    walk(p);
    return firstLine;
  });
}

test("Coffee Q2 단일 paragraph: 좌측 에디터와 우측 PDF 첫 줄 글자 동일", async ({ page }) => {
  // fixture 가 살아있는 환경에서만. 404 면 skip.
  const resp = await page.request.get(`http://localhost:8000/worksheets/${WORKSHEET_ID}`);
  test.skip(resp.status() === 404, "fixture worksheet 가 DB 에 없음");

  await page.goto(`/worksheets/${WORKSHEET_ID}/edit`);
  await page.waitForTimeout(3000);

  // Q2 (Coffee — 단일 paragraph) 탭 선택.
  const tabs = page.locator("button", { hasText: /^\d+\./ });
  await tabs.nth(1).click();
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: "구문분석" }).click();
  await page.waitForTimeout(2000);

  const editorIframe = page.frameLocator('iframe[title="구문분석 에디터"]');
  const proseMirror = editorIframe.locator(".ProseMirror").first();
  const editorFirstLine = await getFirstLineText(proseMirror);

  const previewIframe = page.frameLocator('iframe[title*="미리보기"]');
  const qContents = previewIframe.locator(".q-content");
  const pdfFirstLine = await getFirstLineText(qContents.nth(1));

  expect(editorFirstLine).toBe(pdfFirstLine);
});
