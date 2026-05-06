/**
 * colorUtils — annotation 색상 관련 공통 유틸
 *
 * colorVar() 를 bracket / topLabel / bottomLabel 세 extension 이 공유한다.
 * 중복 정의 방지 — 팔레트 확장 또는 버그 수정 시 이 파일 1곳만 변경한다.
 */

/**
 * colorIndex → CSS 변수명 (EditorPoc.css --anno-color-N 과 동기화).
 *
 * @param colorIndex 1~12 범위의 정수. null 이거나 범위 밖이면 --anno-color-0 반환.
 */
export function colorVar(colorIndex: number | null): string {
  if (colorIndex == null || colorIndex < 1 || colorIndex > 12) return "var(--anno-color-0)";
  return `var(--anno-color-${colorIndex})`;
}
