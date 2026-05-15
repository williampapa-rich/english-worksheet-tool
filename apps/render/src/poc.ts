/**
 * Stage F1 PoC 메인 진입점
 *
 * 사용법:
 *   node --experimental-vm-modules dist/poc.js
 *
 * 또는 ts-node / vitest 에서 import 후 개별 함수 호출.
 */

import {
  C1_ANNOTATIONS,
  C1_PASSAGE,
  C2_ANNOTATIONS,
  C2_PASSAGE,
  C3_ANNOTATIONS,
  C3_PASSAGE,
  ZERO_WASTE_ANNOTATIONS,
  ZERO_WASTE_PASSAGE,
} from "./fixtures/zeroWaste.js";
import {
  renderToHTMLViaGenerateHTML,
  renderToHTMLViaProseMirrorView,
  runCompatibilityCheck,
} from "./serverRenderer.js";

async function main() {
  console.log("=== Stage F1 Server-side Tiptap PoC ===\n");

  // ── F1-d: 호환성 체크 ──────────────────────────────────────────────────────
  console.log("## F1-d: 호환성 체크 실행 중...");
  const compat = await runCompatibilityCheck();
  console.log("\n### jsdom");
  console.log(`  boots: ${compat.jsdom.boots}`);
  console.log(`  generateHTML: ${compat.jsdom.generateHTML_works}`);
  console.log(`  ProseMirror View: ${compat.jsdom.prosemirror_view_works}`);
  console.log(`  Decoration.widget: ${compat.jsdom.decoration_widget_works}`);
  if (compat.jsdom.unsupported_apis.length > 0) {
    console.log("  미지원 API:");
    for (const api of compat.jsdom.unsupported_apis) {
      console.log(`    - ${api}`);
    }
  }
  if (compat.jsdom.errors.length > 0) {
    console.log("  오류:");
    for (const err of compat.jsdom.errors) {
      console.log(`    - ${err}`);
    }
  }

  console.log("\n### linkedom");
  console.log(`  boots: ${compat.linkedom.boots}`);
  if (compat.linkedom.errors.length > 0) {
    console.log("  오류:");
    for (const err of compat.linkedom.errors) {
      console.log(`    - ${err}`);
    }
  }

  console.log(`\n### 권장: ${compat.recommended}`);
  console.log(`  ${compat.notes}`);

  // ── F1-c: C1/C2/C3 시나리오 HTML 출력 ──────────────────────────────────────
  console.log("\n## F1-c: 핵심 검증 시나리오 HTML 출력");

  const scenarios = [
    { name: "C1", passage: C1_PASSAGE, annotations: C1_ANNOTATIONS },
    { name: "C2", passage: C2_PASSAGE, annotations: C2_ANNOTATIONS },
    { name: "C3", passage: C3_PASSAGE, annotations: C3_ANNOTATIONS },
  ];

  for (const scenario of scenarios) {
    console.log(`\n### ${scenario.name}: ${scenario.passage.paragraphs[0]?.slice(0, 60)}...`);

    // generateHTML 경로
    const genResult = renderToHTMLViaGenerateHTML(scenario.passage, scenario.annotations);
    if (genResult.error) {
      console.log(`  [generateHTML] ERROR: ${genResult.error}`);
    } else {
      console.log(`  [generateHTML] OK (${genResult.html.length} chars)`);
      console.log(`    HTML: ${genResult.html.slice(0, 200)}`);
    }

    // ProseMirror View 경로
    const viewResult = await renderToHTMLViaProseMirrorView(scenario.passage, scenario.annotations);
    if (viewResult.error) {
      console.log(`  [ProseMirror View] ERROR: ${viewResult.error}`);
    } else {
      console.log(
        `  [ProseMirror View] OK — widgets found: ${viewResult.widgetsFound} (${viewResult.html.length} chars)`
      );
      console.log(`    HTML: ${viewResult.html.slice(0, 200)}`);
    }
  }

  // ── Zero Waste 전체 passage ─────────────────────────────────────────────────
  console.log("\n## Zero Waste 전체 passage (7 paragraphs)");
  const zwGenResult = renderToHTMLViaGenerateHTML(ZERO_WASTE_PASSAGE, ZERO_WASTE_ANNOTATIONS);
  if (zwGenResult.error) {
    console.log(`  ERROR: ${zwGenResult.error}`);
  } else {
    console.log(`  [generateHTML] OK (${zwGenResult.html.length} chars)`);
    console.log(`    paragraphs 수: ${ZERO_WASTE_PASSAGE.paragraphs.length}`);
    console.log(`    annotation 수: ${ZERO_WASTE_ANNOTATIONS.length}`);
    // 각 paragraph 가 별도 <p> 로 출력되는지 확인
    const pCount = (zwGenResult.html.match(/<p[^>]*>/g) ?? []).length;
    console.log(`    <p> 태그 수: ${pCount} (예상: ${ZERO_WASTE_PASSAGE.paragraphs.length})`);
  }

  const zwViewResult = await renderToHTMLViaProseMirrorView(
    ZERO_WASTE_PASSAGE,
    ZERO_WASTE_ANNOTATIONS
  );
  if (zwViewResult.error) {
    console.log(`  [View] ERROR: ${zwViewResult.error}`);
  } else {
    console.log(
      `  [ProseMirror View] OK — widgets: ${zwViewResult.widgetsFound}, HTML: ${zwViewResult.html.length} chars`
    );
  }

  // ── 결론 ────────────────────────────────────────────────────────────────────
  console.log("\n## F1 PoC 결론");
  const f2Feasible = compat.jsdom.generateHTML_works || compat.jsdom.prosemirror_view_works;
  console.log(`F2 진입 가능: ${f2Feasible ? "YES" : "NO"}`);

  if (compat.jsdom.prosemirror_view_works && compat.jsdom.decoration_widget_works) {
    console.log("권장 경로: ProseMirror View (jsdom) — Decoration.widget 포함 완전 정합.");
  } else if (compat.jsdom.generateHTML_works) {
    console.log("권장 경로: generateHTML — mark 구조 정합. widget 은 후처리 주입 필요.");
  } else {
    console.log("추가 조사 필요 — F1-d 결과 기반 대안 평가 요망.");
  }

  return { compat, f2Feasible };
}

// ESM 직접 실행 시
main().catch(console.error);
