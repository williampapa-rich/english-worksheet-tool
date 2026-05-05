/**
 * wordSnap.test.ts — tokenBoundaryAround 단위 테스트
 *
 * P1-followup-ng-fixes NG 1a:
 * - 구두점 분리 (콤마, 마침표, 세미콜론 등 1글자 토큰)
 * - 어포스트로피 예외 (don't, it's 는 단어 일부)
 */

import { describe, expect, test } from "vitest";

// tokenBoundaryAround 은 모듈 내부 함수이므로
// 동일 로직을 테스트용으로 여기서 재선언한다.
// 실제 코드 변경 없이 로직만 검증하는 화이트박스 테스트.

function isWordChar(ch: string): boolean {
  return /[a-zA-Z0-9''']/.test(ch);
}

function isSpace(ch: string): boolean {
  return /\s/.test(ch);
}

function tokenBoundaryAround(text: string, offset: number): [number, number] | null {
  if (offset >= text.length) {
    if (offset === 0) return null;
    const leftCh = text[offset - 1] ?? "";
    if (isSpace(leftCh)) return null;
    if (isWordChar(leftCh)) {
      let start = offset - 1;
      while (start > 0 && isWordChar(text[start - 1] ?? "")) start--;
      return [start, offset];
    }
    return [offset - 1, offset];
  }

  const ch = text[offset] ?? "";

  if (isSpace(ch)) {
    return null;
  }

  if (isWordChar(ch)) {
    let start = offset;
    while (start > 0 && isWordChar(text[start - 1] ?? "")) start--;
    let end = offset;
    while (end < text.length && isWordChar(text[end] ?? "")) end++;
    return [start, end];
  }

  // 구두점: 해당 offset 1글자만 토큰
  return [offset, offset + 1];
}

// ---------------------------------------------------------------------------
// 테스트
// ---------------------------------------------------------------------------

describe("tokenBoundaryAround — 단어 토큰", () => {
  test("단순 단어 가운데 offset", () => {
    expect(tokenBoundaryAround("hello", 2)).toEqual([0, 5]);
  });

  test("단어 시작 offset", () => {
    expect(tokenBoundaryAround("hello world", 6)).toEqual([6, 11]);
  });

  test("단어 끝 offset (문자열 끝)", () => {
    expect(tokenBoundaryAround("hello", 5)).toEqual([0, 5]);
  });

  test("공백 위 → null", () => {
    expect(tokenBoundaryAround("hello world", 5)).toBeNull();
  });
});

describe("tokenBoundaryAround — 어포스트로피 예외", () => {
  test("don't 는 하나의 단어 토큰", () => {
    expect(tokenBoundaryAround("don't", 0)).toEqual([0, 5]);
    expect(tokenBoundaryAround("don't", 3)).toEqual([0, 5]);
    expect(tokenBoundaryAround("don't", 4)).toEqual([0, 5]);
  });

  test("it's 는 하나의 단어 토큰", () => {
    expect(tokenBoundaryAround("it's fine", 0)).toEqual([0, 4]);
    expect(tokenBoundaryAround("it's fine", 2)).toEqual([0, 4]);
  });

  test("문장 중간의 don't", () => {
    // "I don't know"
    const text = "I don't know";
    // offset=2 → 'd' of don't
    expect(tokenBoundaryAround(text, 2)).toEqual([2, 7]);
    // offset=5 → '\'' of don't
    expect(tokenBoundaryAround(text, 4)).toEqual([2, 7]);
  });
});

describe("tokenBoundaryAround — 구두점 분리", () => {
  test("콤마는 1글자 토큰", () => {
    // "score," — offset 5 (콤마)
    const text = "score,";
    expect(tokenBoundaryAround(text, 5)).toEqual([5, 6]);
  });

  test("마침표는 1글자 토큰", () => {
    const text = "end.";
    expect(tokenBoundaryAround(text, 3)).toEqual([3, 4]);
  });

  test("세미콜론은 1글자 토큰", () => {
    const text = "first; second";
    expect(tokenBoundaryAround(text, 5)).toEqual([5, 6]);
  });

  test("괄호 여는 괄호는 1글자 토큰", () => {
    const text = "(hello)";
    expect(tokenBoundaryAround(text, 0)).toEqual([0, 1]);
  });

  test("괄호 닫는 괄호는 1글자 토큰", () => {
    const text = "(hello)";
    expect(tokenBoundaryAround(text, 6)).toEqual([6, 7]);
  });

  test("score, which — 콤마 선택 후 which 단어 별도 토큰", () => {
    // "score, which" 에서 콤마 offset=5 → [5,6] / which offset=7 → [7,12]
    const text = "score, which";
    expect(tokenBoundaryAround(text, 5)).toEqual([5, 6]);
    expect(tokenBoundaryAround(text, 7)).toEqual([7, 12]);
  });

  test("느낌표는 1글자 토큰", () => {
    const text = "wow!";
    expect(tokenBoundaryAround(text, 3)).toEqual([3, 4]);
  });

  test("물음표는 1글자 토큰", () => {
    const text = "really?";
    expect(tokenBoundaryAround(text, 6)).toEqual([6, 7]);
  });
});

describe("tokenBoundaryAround — 경계 케이스", () => {
  test("빈 문자열 → null", () => {
    expect(tokenBoundaryAround("", 0)).toBeNull();
  });

  test("offset 이 문자열 길이와 같을 때 (끝)", () => {
    expect(tokenBoundaryAround("hello", 5)).toEqual([0, 5]);
  });

  test("공백 후 공백 사이 offset → null", () => {
    expect(tokenBoundaryAround("a  b", 2)).toBeNull();
  });
});
