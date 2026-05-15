/**
 * serverRenderer — Stage F1: Node.js + jsdom 환경에서 Tiptap HTML 생성
 *
 * ADR-0018 §Stage F1 PoC.
 *
 * 전략 (사전 가이드 §1.2 대안 분석):
 *
 *   시도 1: @tiptap/html generateHTML() — mark 기반 정적 HTML.
 *     - Decoration.widget (bracket / top_label / bottom_label 의 실제 글자 / 라벨 텍스트)
 *       은 이 경로에서 출력되지 않음.
 *     - mark span (data-annotation-kind, data-bracket-style 등) 은 정상 출력.
 *     - 즉 에디터 측 HTML 과 구조는 같지만 widget DOM 노드가 없음.
 *
 *   시도 2: ProseMirror View 를 jsdom 위에서 직접 띄우기 (대안 1).
 *     - View 는 브라우저 이벤트 / focus / 마우스 처리를 포함 → jsdom 호환성 검증 필요.
 *     - boot 시 DOM 오류가 없으면 decoration.widget 이 View.dom 에 포함됨.
 *     - F1-b 에서 호환성 검증.
 *
 *   결론 (F1-d 에서 최종 판단):
 *     generateHTML 경로: 에디터 mark 구조 (span class / data-attr) 정합 검증 가능.
 *     ProseMirror View 경로: decoration.widget 포함 완전 정합.
 *
 * jsdom 설정:
 *   global.document / window / Node 주입 — @tiptap/core, @tiptap/pm 이 이것에 의존.
 *   Range / Selection 은 jsdom 에서 부분 지원 (완전 layout 은 없음).
 */

import { JSDOM } from "jsdom";

// jsdom 전역 주입 — @tiptap/core 가 import 시점에 document 에 접근
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

import { generateHTML } from "@tiptap/html";
import StarterKit from "@tiptap/starter-kit";

import { BottomLabelMark } from "@english-worksheet-tool/editor";
import { BracketMark } from "@english-worksheet-tool/editor";
import { HighlightMark } from "@english-worksheet-tool/editor";
import { InlineNoteMark } from "@english-worksheet-tool/editor";
import { TopLabelMark } from "@english-worksheet-tool/editor";
import { UnderlineMark } from "@english-worksheet-tool/editor";

import { annotationsToTiptapDoc } from "./annotationsToTiptapDoc.js";
import type {
  CompatibilityReport,
  PassageForRender,
  SyntaxAnnotation,
  TiptapDoc,
} from "./types.js";

/**
 * 에디터 extensions 목록 (apps/web EditorPoc.tsx 와 동일하게 구성)
 */
function getExtensions() {
  return [
    StarterKit,
    HighlightMark,
    UnderlineMark,
    TopLabelMark,
    BottomLabelMark,
    BracketMark,
    InlineNoteMark,
  ];
}

/**
 * generateHTML 경로 — Tiptap JSON doc → HTML 문자열.
 *
 * Decoration.widget 은 포함되지 않음 (mark span 만).
 * 에디터 측 출력의 mark 구조 정합 검증 용도.
 */
export function renderToHTMLViaGenerateHTML(
  passage: PassageForRender,
  annotations: SyntaxAnnotation[]
): { html: string; doc: TiptapDoc; error: string | null } {
  try {
    const doc = annotationsToTiptapDoc(passage, annotations);
    const extensions = getExtensions();
    // biome-ignore lint/suspicious/noExplicitAny: Tiptap typing
    const html = generateHTML(doc as any, extensions as any);
    return { html, doc, error: null };
  } catch (e) {
    return {
      html: "",
      doc: { type: "doc", content: [] },
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

/**
 * ProseMirror View 경로 — jsdom DOM 위에서 View 직접 boot.
 *
 * decoration.widget 이 View.dom 에 반영되는지 검증 (F1-b 핵심 체크).
 * boot 성공 시 innerHTML 반환.
 */
export async function renderToHTMLViaProseMirrorView(
  passage: PassageForRender,
  annotations: SyntaxAnnotation[]
): Promise<{ html: string; widgetsFound: number; error: string | null }> {
  try {
    const { EditorState } = await import("@tiptap/pm/state");
    const { EditorView } = await import("@tiptap/pm/view");
    const { Editor } = await import("@tiptap/core");

    const doc = annotationsToTiptapDoc(passage, annotations);
    const extensions = getExtensions();

    const editor = new Editor({
      // biome-ignore lint/suspicious/noExplicitAny: Tiptap extensions typing
      extensions: extensions as any,
      // biome-ignore lint/suspicious/noExplicitAny: Tiptap content typing
      content: doc as any,
      element: dom.window.document.createElement("div"),
      injectCSS: false,
    });

    // View DOM 에서 widget 수 계산 (bracket, top_label, bottom_label widget)
    const view = editor.view;
    const domEl = view.dom as HTMLElement;
    const widgetEls = domEl.querySelectorAll(
      "[data-top-label-widget], [data-bottom-label-widget], [data-bracket-widget]"
    );
    const widgetsFound = widgetEls.length;
    const html = domEl.innerHTML;

    editor.destroy();
    return { html, widgetsFound, error: null };
  } catch (e) {
    return {
      html: "",
      widgetsFound: 0,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

/**
 * F1-d: jsdom / linkedom 호환성 평가
 */
export async function runCompatibilityCheck(): Promise<CompatibilityReport> {
  const jsdomReport: CompatibilityReport["jsdom"] = {
    boots: false,
    generateHTML_works: false,
    prosemirror_view_works: false,
    decoration_widget_works: false,
    unsupported_apis: [],
    errors: [],
  };

  // 1. jsdom 기본 boot 확인
  try {
    const testDom = new JSDOM("<!DOCTYPE html><html><body><p>test</p></body></html>", {
      url: "http://localhost",
    });
    const text = testDom.window.document.querySelector("p")?.textContent;
    jsdomReport.boots = text === "test";
  } catch (e) {
    jsdomReport.errors.push(`jsdom boot: ${String(e)}`);
  }

  // 2. generateHTML 경로
  try {
    const simplePassage: PassageForRender = {
      body_text: "Hello world test",
      paragraphs: ["Hello world test"],
    };
    const result = renderToHTMLViaGenerateHTML(simplePassage, []);
    jsdomReport.generateHTML_works = result.error === null && result.html.includes("Hello world");
    if (result.error) jsdomReport.errors.push(`generateHTML: ${result.error}`);
  } catch (e) {
    jsdomReport.errors.push(`generateHTML: ${String(e)}`);
  }

  // 3. ProseMirror View boot
  try {
    const simplePassage: PassageForRender = {
      body_text: "Hello world test",
      paragraphs: ["Hello world test"],
    };
    const viewResult = await renderToHTMLViaProseMirrorView(simplePassage, []);
    jsdomReport.prosemirror_view_works = viewResult.error === null;
    if (viewResult.error) jsdomReport.errors.push(`View: ${viewResult.error}`);
  } catch (e) {
    jsdomReport.errors.push(`View: ${String(e)}`);
  }

  // 4. Decoration.widget 검증 (bracket 하나 추가)
  try {
    const testPassage: PassageForRender = {
      body_text: "Hello world test",
      paragraphs: ["Hello world test"],
    };
    const testAnn: SyntaxAnnotation[] = [
      {
        kind: "bracket",
        span: { span_format: "character_offset_v1", start: 6, end: 11 },
        bracket_style: "()",
        annotation_id: "test-ann-1",
      },
    ];
    const viewResult = await renderToHTMLViaProseMirrorView(testPassage, testAnn);
    jsdomReport.decoration_widget_works = viewResult.error === null && viewResult.widgetsFound > 0;
    if (viewResult.error) jsdomReport.errors.push(`widget: ${viewResult.error}`);
  } catch (e) {
    jsdomReport.errors.push(`widget: ${String(e)}`);
  }

  // 5. jsdom layout API 확인
  try {
    const el = dom.window.document.createElement("span");
    el.textContent = "test";
    dom.window.document.body.appendChild(el);
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      jsdomReport.unsupported_apis.push(
        "getBoundingClientRect() — always {0,0,0,0} (layout 미지원)"
      );
    }
    // Range.getBoundingClientRect
    const range = dom.window.document.createRange();
    range.selectNodeContents(el);
    const rangeRect = range.getBoundingClientRect();
    if (rangeRect.width === 0) {
      jsdomReport.unsupported_apis.push("Range.getBoundingClientRect() — always {0,0,0,0}");
    }
    dom.window.document.body.removeChild(el);
  } catch (e) {
    jsdomReport.errors.push(`layout API: ${String(e)}`);
  }

  // 6. linkedom 간단 boot 시도
  const linkedomReport: CompatibilityReport["linkedom"] = {
    boots: false,
    errors: [],
  };
  try {
    const { parseHTML } = await import("linkedom");
    const { document: ldDoc } = parseHTML(
      "<!DOCTYPE html><html><body><p>linkedom test</p></body></html>"
    );
    const text = (ldDoc as Document).querySelector("p")?.textContent;
    linkedomReport.boots = text === "linkedom test";
  } catch (e) {
    linkedomReport.errors.push(String(e));
  }

  return {
    jsdom: jsdomReport,
    linkedom: linkedomReport,
    recommended: jsdomReport.prosemirror_view_works ? "jsdom" : "neither",
    notes: jsdomReport.prosemirror_view_works
      ? "ProseMirror View가 jsdom 위에서 동작 → Decoration.widget 포함 완전 정합 가능"
      : "ProseMirror View boot 실패 — generateHTML 경로 + 후처리로 대안 검토 필요",
  };
}
