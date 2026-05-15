/**
 * Stage F2 CLI 진입점 — Python subprocess 에서 호출되는 server-side Tiptap 렌더러.
 *
 * ADR-0018 Stage F2 산출물 F2-a.
 *
 * 프로토콜:
 *   stdin  → JSON: { passage: PassageForRender, annotations: SyntaxAnnotation[] }
 *   stdout → HTML 문자열 (에러 없을 때)
 *   stderr → 에러 메시지 (에러 발생 시)
 *   exit 0 → 성공
 *   exit 1 → 실패
 *
 * 사용 예시 (Python subprocess):
 *   echo '{"passage": {...}, "annotations": [...]}' | node dist/bin.js
 *
 * 설계 결정 (subprocess vs HTTP 마이크로서비스):
 *   - subprocess 채택: 추가 프로세스 관리 불필요, Dockerfile 단순.
 *   - 트레이드오프: 매 호출 Node.js 콜드 스타트 ~200ms (jsdom + Tiptap import).
 *   - preview 라우트 응답 시간 허용: 총 ~500ms (렌더 포함) → UX 허용 범위.
 *   - PDF export 는 이미 Playwright 시간이 지배적 → subprocess overhead 미미.
 *   - HTTP 마이크로서비스로 전환 필요 시: bin.ts → Express 서버로 교체, Python
 *     wrapper 의 subprocess call → httpx call 로 교체만 하면 됨.
 */

import { JSDOM } from "jsdom";

// jsdom 전역 주입 — @tiptap/core 가 import 시점에 document 에 접근.
// serverRenderer.ts 와 동일한 polyfill 패턴.
const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
  url: "http://localhost",
});

// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).window = dom.window;
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).document = dom.window.document;
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).Node = dom.window.Node;
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).NodeList = dom.window.NodeList;
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).HTMLElement = dom.window.HTMLElement;
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).Element = dom.window.Element;
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).MutationObserver = dom.window.MutationObserver;
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).Range = dom.window.Range;
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).Selection = dom.window.Selection;
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).DOMParser = dom.window.DOMParser;
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).getSelection = () => dom.window.getSelection();
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).requestAnimationFrame = (cb: FrameRequestCallback) => setTimeout(cb, 0);
// biome-ignore lint/suspicious/noExplicitAny: global polyfill
(globalThis as any).cancelAnimationFrame = (id: number) => clearTimeout(id);

// --- Tiptap imports (전역 주입 이후) ---
import { renderToHTMLViaProseMirrorView } from "./serverRenderer.js";
import type { PassageForRender, SyntaxAnnotation } from "./types.js";

/**
 * CLI 입력 스키마 — Python에서 전달하는 JSON 형식.
 */
interface CliInput {
  passage: PassageForRender;
  annotations: SyntaxAnnotation[];
}

/**
 * stdin에서 JSON을 읽어 server-side Tiptap으로 HTML을 렌더링한다.
 *
 * 성공: stdout에 HTML 문자열 출력 후 exit 0.
 * 실패: stderr에 에러 메시지 출력 후 exit 1.
 */
async function main(): Promise<void> {
  let rawInput = "";

  // stdin 수집
  process.stdin.setEncoding("utf-8");
  for await (const chunk of process.stdin) {
    rawInput += chunk;
  }

  // JSON 파싱
  let input: CliInput;
  try {
    input = JSON.parse(rawInput) as CliInput;
  } catch (e) {
    process.stderr.write(`[bin.ts] JSON parse error: ${String(e)}\n`);
    process.exit(1);
  }

  // 입력 검증
  if (!input.passage || typeof input.passage.body_text !== "string") {
    process.stderr.write("[bin.ts] Invalid input: passage.body_text is required\n");
    process.exit(1);
  }
  if (!Array.isArray(input.annotations)) {
    process.stderr.write("[bin.ts] Invalid input: annotations must be an array\n");
    process.exit(1);
  }

  // ProseMirror View 경로 — Decoration.widget 포함 완전 정합.
  // generateHTML 경로 대비 장점: bracket / label widget DOM 이 실제로 포함됨.
  const result = await renderToHTMLViaProseMirrorView(input.passage, input.annotations);

  if (result.error) {
    process.stderr.write(`[bin.ts] Render error: ${result.error}\n`);
    process.exit(1);
  }

  // stdout에 HTML 출력 (trailing newline 없음 — Python이 그대로 사용)
  process.stdout.write(result.html);
  process.exit(0);
}

main().catch((e: unknown) => {
  process.stderr.write(`[bin.ts] Uncaught error: ${String(e)}\n`);
  process.exit(1);
});
