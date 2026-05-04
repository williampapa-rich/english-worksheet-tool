/**
 * api-mock.ts — Playwright E2E API mock 헬퍼 (P1-6b)
 *
 * 목적: FastAPI/DB 를 띄우지 않고 apps/web/src/lib/api.ts 가 호출하는
 *       backend 엔드포인트를 page.route() 로 정적 fixture 응답으로 대체.
 *
 * 패턴:
 *   - api.ts 의 API_BASE_URL = "http://localhost:8000" (VITE_API_BASE_URL 미설정 fallback)
 *   - page.route 의 glob 패턴으로 "http://localhost:8000/passages/**" 가로챔.
 *   - 응답 형태는 shared/schemas/ + apps/api/src/worksheet_api/routers/ 와 일치시킴.
 *
 * 사용:
 *   await setupApiMocks(page, { passageId: 'test-passage-1' });
 */

import type { Page, Route } from "@playwright/test";

const API_BASE = "http://localhost:8000";

export interface MockOptions {
  passageId: string;
  /** 에디터에 로드될 본문 텍스트 (단일 단락). 기본값 제공. */
  bodyText?: string;
}

/** POST /passages/:id/annotations 요청에서 annotations 를 꺼내 id 부여 후 echo */
async function echoAnnotations(route: Route): Promise<void> {
  let body: { annotations?: unknown[] } = {};
  try {
    body = (await route.request().postDataJSON()) as { annotations?: unknown[] };
  } catch {
    // postData 없거나 JSON 파싱 실패
  }
  const annotations = (body.annotations ?? []) as Record<string, unknown>[];
  const saved = annotations.map((ann, i) => ({
    ...ann,
    id: `mock-ann-${i + 1}`,
    passage_id: route.request().url().split("/passages/")[1]?.split("/")[0] ?? "unknown",
  }));
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ annotations: saved }),
  });
}

/**
 * setupApiMocks — 테스트 시작 전 page.route() 등록.
 *
 * 등록 순서: POST 를 GET 보다 먼저 등록 (glob 이 겹치는 경우 순서 우선).
 * GET /passages/:id/hwpx 는 zip 시그니처 더미 바이트 반환 — 브라우저 다운로드 트리거용.
 */
export async function setupApiMocks(page: Page, opts: MockOptions): Promise<void> {
  const { passageId } = opts;
  const bodyText =
    opts.bodyText ??
    "The student who had studied hard for the exam passed with an excellent score.";

  const passageBase = `${API_BASE}/passages/${passageId}`;

  // POST /passages/:id/annotations — annotations echo
  await page.route(`${passageBase}/annotations`, async (route) => {
    if (route.request().method() === "POST") {
      await echoAnnotations(route);
    } else {
      // GET — annotations 빈 배열 반환 (초기 상태)
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ annotations: [] }),
      });
    }
  });

  // GET /passages/:id/hwpx — 더미 zip 바이트 (PK 시그니처)
  await page.route(`${passageBase}/hwpx`, async (route) => {
    // PK (0x50 0x4b 0x03 0x04) — ZIP 로컬 파일 헤더 시그니처
    const zipMagic = Buffer.from([0x50, 0x4b, 0x03, 0x04, 0x00, 0x00, 0x00, 0x00]);
    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "application/hwp+zip",
        "Content-Disposition": `attachment; filename="passage_${passageId}.hwpx"`,
      },
      body: zipMagic,
    });
  });

  // GET /passages/:id — passage 객체 반환
  await page.route(passageBase, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        passage: {
          id: passageId,
          body_text: bodyText,
          paragraphs: [bodyText],
          title: null,
          source_material: null,
        },
        questions: [],
      }),
    });
  });
}
