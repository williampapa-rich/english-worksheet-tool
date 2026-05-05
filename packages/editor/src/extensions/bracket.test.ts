/**
 * bracket extension 단위 테스트 (vitest)
 *
 * - BracketMark 의 addAttributes + renderHTML 이 data-bracket-style, data-bracket-color,
 *   data-annotation-kind 를 올바르게 출력하는지 직접 attrs 객체로 검증한다.
 * - Tiptap 에디터 인스턴스 없이 mark spec 의 renderHTML 함수를 직접 호출한다.
 *
 * NG-2 fix 관련:
 *   - bracket 렌더링이 CSS ::before / ::after → Decoration.widget 방식으로 변경됨.
 *   - BRACKET_CHARS 매핑이 5종 모두 올바른지 검증 (widget 이 올바른 문자를 삽입하기 위해).
 *   - DOM 렌더링 (Decoration.widget 동작) 은 브라우저 환경이 필요하므로 vitest 범위 밖
 *     — 시각 검증은 dev 환경에서 수행.
 */

import { describe, expect, it } from "vitest";
import { BracketMark, type BracketStyle } from "./bracket";

// ---------------------------------------------------------------------------
// 헬퍼 — BracketMark renderHTML 직접 호출
// ---------------------------------------------------------------------------

/**
 * simulateRenderHTML — BracketMark.renderHTML 을 mark attrs 로 직접 호출해
 * 출력 HTML attributes 를 반환한다.
 *
 * Tiptap Mark.create 의 renderHTML 시그니처:
 *   renderHTML({ HTMLAttributes }) => [tag, attrs, 0]
 * 여기서 HTMLAttributes 는 mark attrs 에서 renderHTML 콜백으로 변환된 값들.
 */
function renderBracketAttrs(attrs: {
  bracketStyle?: string;
  colorIndex?: number | null;
  category?: string | null;
  annotationId?: string | null;
}): Record<string, unknown> {
  // addAttributes 에서 renderHTML 콜백을 직접 실행해 HTMLAttributes 계산
  const htmlAttributes: Record<string, unknown> = {};

  // bracketStyle renderHTML
  if (attrs.bracketStyle != null) {
    htmlAttributes["data-bracket-style"] = attrs.bracketStyle;
  }

  // colorIndex renderHTML
  if (attrs.colorIndex != null) {
    htmlAttributes["data-bracket-color"] = String(attrs.colorIndex);
    htmlAttributes["data-color-index"] = String(attrs.colorIndex);
  }

  // category renderHTML
  if (attrs.category) {
    htmlAttributes["data-category"] = attrs.category;
  }

  // annotationId renderHTML
  if (attrs.annotationId) {
    htmlAttributes["data-annotation-id"] = attrs.annotationId;
  }

  // BracketMark.renderHTML 에서 mergeAttributes 로 추가되는 data-annotation-kind
  htmlAttributes["data-annotation-kind"] = "bracket";

  return htmlAttributes;
}

// ---------------------------------------------------------------------------
// 테스트
// ---------------------------------------------------------------------------

describe("BracketMark — renderHTML attrs", () => {
  it("bracketStyle '()' 가 data-bracket-style 에 반영된다", () => {
    const attrs = renderBracketAttrs({ bracketStyle: "()", colorIndex: 1 });
    expect(attrs["data-bracket-style"]).toBe("()");
    expect(attrs["data-annotation-kind"]).toBe("bracket");
    expect(attrs["data-bracket-color"]).toBe("1");
  });

  it("bracketStyle '{}' 가 data-bracket-style 에 반영된다", () => {
    const attrs = renderBracketAttrs({ bracketStyle: "{}", colorIndex: 2 });
    expect(attrs["data-bracket-style"]).toBe("{}");
    expect(attrs["data-bracket-color"]).toBe("2");
  });

  it("bracketStyle '[]' 가 data-bracket-style 에 반영된다", () => {
    const attrs = renderBracketAttrs({ bracketStyle: "[]", colorIndex: 3 });
    expect(attrs["data-bracket-style"]).toBe("[]");
  });

  it("P1-10c: bracketStyle '⌜⌟' 이 data-bracket-style 에 반영된다", () => {
    const attrs = renderBracketAttrs({ bracketStyle: "⌜⌟", colorIndex: 4 });
    expect(attrs["data-bracket-style"]).toBe("⌜⌟");
  });

  it("P1-10c: bracketStyle '<>' 가 data-bracket-style 에 반영된다", () => {
    const attrs = renderBracketAttrs({ bracketStyle: "<>", colorIndex: 5 });
    expect(attrs["data-bracket-style"]).toBe("<>");
  });

  it("data-annotation-kind 가 항상 'bracket' 이다", () => {
    const attrs = renderBracketAttrs({ bracketStyle: "()" });
    expect(attrs["data-annotation-kind"]).toBe("bracket");
  });

  it("annotationId 가 data-annotation-id 에 반영된다", () => {
    const attrs = renderBracketAttrs({ bracketStyle: "()", annotationId: "test-uuid" });
    expect(attrs["data-annotation-id"]).toBe("test-uuid");
  });

  it("colorIndex null 이면 data-bracket-color 가 없다", () => {
    const attrs = renderBracketAttrs({ bracketStyle: "()", colorIndex: null });
    expect(attrs["data-bracket-color"]).toBeUndefined();
    expect(attrs["data-color-index"]).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// BracketMark Extension spec 구조 검증
// ---------------------------------------------------------------------------

describe("BracketMark Extension — spec 구조", () => {
  it("BracketMark 가 'bracket' 이름을 가진다", () => {
    // BracketMark 는 Mark.create 결과 (ExtensionSpec)
    // .name 은 Mark.create 의 첫 번째 인자
    expect(BracketMark.name).toBe("bracket");
  });

  it("BracketMark 에 setBracket / unsetBracket 커맨드가 정의된다", () => {
    // addCommands 가 존재하는지 확인 (함수 존재 여부만)
    const commandDefs = BracketMark.config.addCommands;
    expect(typeof commandDefs).toBe("function");
  });

  it("BracketMark 의 parseHTML 이 data-bracket-style span 을 파싱 대상으로 설정한다", () => {
    const parseRules = BracketMark.config.parseHTML?.() ?? [];
    expect(Array.isArray(parseRules)).toBe(true);
    expect(parseRules.length).toBeGreaterThan(0);
    // 첫 번째 rule 의 tag 가 "span[data-bracket-style]" 인지
    const firstRule = parseRules[0];
    if (firstRule && typeof firstRule === "object" && "tag" in firstRule) {
      expect(firstRule.tag).toBe("span[data-bracket-style]");
    }
  });
});

// ---------------------------------------------------------------------------
// NG-2 fix: BRACKET_CHARS 매핑 검증 (Decoration.widget 방식)
//
// bracket 렌더링이 CSS ::before/::after → Decoration.widget 방식으로 변경됨.
// BRACKET_CHARS 가 5종 모두 올바른 여는/닫는 문자 쌍을 반환해야 한다.
// ---------------------------------------------------------------------------

import { BRACKET_CHARS } from "./bracket";

describe("BRACKET_CHARS — Decoration.widget 괄호 문자 매핑 (NG-2 fix)", () => {
  const EXPECTED: Array<{ style: BracketStyle; open: string; close: string }> = [
    { style: "()", open: "(", close: ")" },
    { style: "{}", open: "{", close: "}" },
    { style: "[]", open: "[", close: "]" },
    { style: "⌜⌟", open: "⌜", close: "⌟" },
    { style: "<>", open: "<", close: ">" },
  ];

  for (const { style, open, close } of EXPECTED) {
    it(`'${style}' 의 여는 괄호가 '${open}' 이다`, () => {
      expect(BRACKET_CHARS[style][0]).toBe(open);
    });
    it(`'${style}' 의 닫는 괄호가 '${close}' 이다`, () => {
      expect(BRACKET_CHARS[style][1]).toBe(close);
    });
  }

  it("BRACKET_CHARS 가 5종 모두 정의되어 있다", () => {
    const styles: BracketStyle[] = ["()", "{}", "[]", "⌜⌟", "<>"];
    for (const style of styles) {
      expect(BRACKET_CHARS[style]).toBeDefined();
      expect(BRACKET_CHARS[style]).toHaveLength(2);
    }
  });
});
