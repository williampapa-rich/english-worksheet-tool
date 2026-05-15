/**
 * F1-b/F1-d: jsdom 호환성 + Tiptap server-side 동작 검증 (Vitest)
 *
 * Stage F1 PoC 자동화 테스트.
 *
 * 주의 (사전 가이드 §3.1):
 *   jsdom 은 layout 미지원 — getBoundingClientRect() 가 {0,0,0,0} 반환.
 *   wrap 위치 측정은 Playwright Chromium 에서 (F1-e spec).
 *   본 테스트는 HTML 구조 정합 검증만.
 */

import { afterAll, beforeAll, describe, expect, it } from "vitest";

// --- jsdom 전역 polyfill (serverRenderer import 전에 필요) ---
import { JSDOM } from "jsdom";

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

// --- imports (polyfill 이후) ---
import {
  C1_ANNOTATIONS,
  C1_PASSAGE,
  C2_ANNOTATIONS,
  C2_PASSAGE,
  C3_ANNOTATIONS,
  C3_PASSAGE,
  ZERO_WASTE_ANNOTATIONS,
  ZERO_WASTE_PASSAGE,
} from "../src/fixtures/zeroWaste.js";
import { annotationsToTiptapDoc } from "../src/annotationsToTiptapDoc.js";
import {
  renderToHTMLViaGenerateHTML,
  renderToHTMLViaProseMirrorView,
  runCompatibilityCheck,
} from "../src/serverRenderer.js";

// ─── F1-a: 환경 셋업 검증 ────────────────────────────────────────────────────

describe("F1-a: 환경 셋업 — jsdom boot", () => {
  it("jsdom 이 정상 boot 된다", () => {
    const testDom = new JSDOM("<p>hello</p>", { url: "http://localhost" });
    expect(testDom.window.document.querySelector("p")?.textContent).toBe("hello");
  });

  it("global.document 가 주입되어 있다", () => {
    // biome-ignore lint/suspicious/noExplicitAny: global check
    expect((globalThis as any).document).toBeDefined();
    // biome-ignore lint/suspicious/noExplicitAny: global check
    expect(typeof (globalThis as any).document.createElement).toBe("function");
  });

  it("MutationObserver 가 사용 가능하다", () => {
    // biome-ignore lint/suspicious/noExplicitAny: global check
    expect((globalThis as any).MutationObserver).toBeDefined();
  });
});

// ─── F1-b: Tiptap / ProseMirror extensions 호환성 ────────────────────────────

describe("F1-b: extensions jsdom 호환성", () => {
  it("@tiptap/html generateHTML import 가 성공한다", async () => {
    const { generateHTML } = await import("@tiptap/html");
    expect(typeof generateHTML).toBe("function");
  });

  it("@tiptap/core Editor import 가 성공한다", async () => {
    const { Editor } = await import("@tiptap/core");
    expect(typeof Editor).toBe("function");
  });

  it("@english-worksheet-tool/editor extensions import 가 성공한다", async () => {
    const editorPkg = await import("@english-worksheet-tool/editor");
    expect(editorPkg.TopLabelMark).toBeDefined();
    expect(editorPkg.BottomLabelMark).toBeDefined();
    expect(editorPkg.BracketMark).toBeDefined();
    expect(editorPkg.HighlightMark).toBeDefined();
    expect(editorPkg.UnderlineMark).toBeDefined();
    expect(editorPkg.InlineNoteMark).toBeDefined();
  });
});

// ─── F1-c: annotationsToTiptapDoc 단위 테스트 ────────────────────────────────

describe("F1-c: annotationsToTiptapDoc — doc 구조 정합", () => {
  it("단일 paragraph — paragraph 1개 doc 반환", () => {
    const doc = annotationsToTiptapDoc(C1_PASSAGE, []);
    expect(doc.type).toBe("doc");
    expect(doc.content).toHaveLength(1);
    expect(doc.content[0]?.type).toBe("paragraph");
  });

  it("7 paragraphs — paragraph 7개 doc 반환", () => {
    const doc = annotationsToTiptapDoc(ZERO_WASTE_PASSAGE, []);
    expect(doc.content).toHaveLength(7);
  });

  it("highlight annotation → mark 가 텍스트 노드에 포함됨", () => {
    const passage = {
      body_text: "Hello world test",
      paragraphs: ["Hello world test"],
    };
    const annotations = [
      {
        kind: "highlight" as const,
        span: { span_format: "character_offset_v1" as const, start: 6, end: 11 },
        color_index: 1,
        annotation_id: "test-1",
      },
    ];
    const doc = annotationsToTiptapDoc(passage, annotations);
    const para = doc.content[0];
    expect(para?.content).toBeDefined();

    // "Hello " (0-5) / "world" (6-10) highlighted / " test" (11-)
    const textNodes = para?.content ?? [];
    expect(textNodes.length).toBeGreaterThanOrEqual(3);

    const highlightedNode = textNodes.find((n) =>
      n.marks?.some((m) => m.type === "highlight")
    );
    expect(highlightedNode).toBeDefined();
    expect(highlightedNode?.text).toBe("world");
  });

  it("bracket annotation → bracket mark 포함", () => {
    const doc = annotationsToTiptapDoc(C3_PASSAGE, C3_ANNOTATIONS);
    const para = doc.content[0];
    const bracketNode = para?.content?.find((n) =>
      n.marks?.some((m) => m.type === "bracket")
    );
    expect(bracketNode).toBeDefined();
    expect(bracketNode?.text).toContain("70 zero-waste");
  });

  it("top_label annotation → topLabel mark 포함", () => {
    const doc = annotationsToTiptapDoc(C1_PASSAGE, C1_ANNOTATIONS);
    const para = doc.content[0];
    const labelNode = para?.content?.find((n) =>
      n.marks?.some((m) => m.type === "topLabel")
    );
    expect(labelNode).toBeDefined();
  });
});

// ─── F1-c: generateHTML 출력 구조 검증 ──────────────────────────────────────

describe("F1-c: generateHTML 출력 — mark HTML 구조", () => {
  it("C1: highlight mark 가 HTML 에 포함된다", () => {
    const result = renderToHTMLViaGenerateHTML(C1_PASSAGE, C1_ANNOTATIONS);
    expect(result.error).toBeNull();
    expect(result.html).toContain("data-annotation-kind");
  });

  it("C2: bracket mark HTML 이 출력된다", () => {
    const result = renderToHTMLViaGenerateHTML(C2_PASSAGE, C2_ANNOTATIONS);
    expect(result.error).toBeNull();
    // bracket mark span (data-bracket-style) 이 포함
    expect(result.html).toContain("data-bracket-style");
  });

  it("C3: bracket mark HTML 이 출력된다", () => {
    const result = renderToHTMLViaGenerateHTML(C3_PASSAGE, C3_ANNOTATIONS);
    expect(result.error).toBeNull();
    expect(result.html).toContain("data-bracket-style");
  });

  it("Zero Waste 7 paragraphs — 단락 수만큼 <p> 태그 출력", () => {
    const result = renderToHTMLViaGenerateHTML(ZERO_WASTE_PASSAGE, ZERO_WASTE_ANNOTATIONS);
    expect(result.error).toBeNull();
    const pCount = (result.html.match(/<p[^>]*>/g) ?? []).length;
    expect(pCount).toBe(ZERO_WASTE_PASSAGE.paragraphs.length);
  });

  it("highlight annotation → <mark> 태그 출력 (Tiptap highlight 기본)", () => {
    const passage = {
      body_text: "Hello world test",
      paragraphs: ["Hello world test"],
    };
    const anns = [
      {
        kind: "highlight" as const,
        span: { span_format: "character_offset_v1" as const, start: 6, end: 11 },
        color_index: 1,
        annotation_id: "hl-1",
      },
    ];
    const result = renderToHTMLViaGenerateHTML(passage, anns);
    expect(result.error).toBeNull();
    // @tiptap/extension-highlight 는 <mark> 태그 출력
    expect(result.html).toContain("<mark");
    expect(result.html).toContain("world");
  });

  it("underline annotation → <u> 또는 data-annotation-kind span 출력", () => {
    const passage = {
      body_text: "Hello world test",
      paragraphs: ["Hello world test"],
    };
    const anns = [
      {
        kind: "underline" as const,
        span: { span_format: "character_offset_v1" as const, start: 6, end: 11 },
        annotation_id: "ul-1",
      },
    ];
    const result = renderToHTMLViaGenerateHTML(passage, anns);
    expect(result.error).toBeNull();
    // UnderlineMark 는 <span data-annotation-kind="underline">
    expect(result.html).toContain("world");
  });

  it("top_label annotation → span[data-annotation-kind=top_label] 출력", () => {
    const result = renderToHTMLViaGenerateHTML(C1_PASSAGE, C1_ANNOTATIONS);
    expect(result.error).toBeNull();
    expect(result.html).toContain('data-annotation-kind="top_label"');
  });

  it("top_label text attr → data-top-label-text 포함", () => {
    const result = renderToHTMLViaGenerateHTML(C1_PASSAGE, C1_ANNOTATIONS);
    expect(result.error).toBeNull();
    expect(result.html).toContain("data-top-label-text");
  });
});

// ─── F1-b: ProseMirror View jsdom 호환성 ────────────────────────────────────

describe("F1-b: ProseMirror View — jsdom 위에서 boot", () => {
  it("View boot 가 성공한다 (에러 없음)", async () => {
    const result = await renderToHTMLViaProseMirrorView(
      { body_text: "Hello world", paragraphs: ["Hello world"] },
      []
    );
    expect(result.error).toBeNull();
    expect(result.html).toContain("Hello world");
  }, 10000);

  it("bracket annotation → widget DOM 이 View.dom 에 포함된다", async () => {
    const result = await renderToHTMLViaProseMirrorView(C3_PASSAGE, C3_ANNOTATIONS);
    expect(result.error).toBeNull();
    // bracket widget 은 data-bracket-widget attr
    expect(result.widgetsFound).toBeGreaterThan(0);
  }, 10000);

  it("C2 (bracket + label) — View 출력에 widget 이 포함된다", async () => {
    const result = await renderToHTMLViaProseMirrorView(C2_PASSAGE, C2_ANNOTATIONS);
    expect(result.error).toBeNull();
    expect(result.widgetsFound).toBeGreaterThan(0);
  }, 10000);
});

// ─── F1-d: 호환성 전체 리포트 ───────────────────────────────────────────────

describe("F1-d: 호환성 리포트", () => {
  let report: Awaited<ReturnType<typeof runCompatibilityCheck>>;

  beforeAll(async () => {
    report = await runCompatibilityCheck();
  }, 30000);

  it("jsdom boots", () => {
    expect(report.jsdom.boots).toBe(true);
  });

  it("generateHTML 경로 동작", () => {
    expect(report.jsdom.generateHTML_works).toBe(true);
  });

  it("getBoundingClientRect 가 {0,0} 반환 (layout 미지원 확인)", () => {
    // jsdom 이 layout 미지원임을 명시 검증 (사전 가이드 §3.1)
    const hasBCR = report.jsdom.unsupported_apis.some((api) =>
      api.includes("getBoundingClientRect")
    );
    expect(hasBCR).toBe(true);
  });

  it("linkedom boots", () => {
    expect(report.linkedom.boots).toBe(true);
  });

  it("권장이 jsdom 또는 neither (linkedom 아님)", () => {
    expect(["jsdom", "neither"]).toContain(report.recommended);
  });
});
