/**
 * AnalysisTable — 분석표 컴포넌트 (P1-2b)
 *
 * annotation 목록을 카테고리 6행으로 정리해 칩으로 표시한다.
 * 칩 x 버튼이 같은 annotationId 의 모든 mark range 를 통째 unset 한다.
 *
 * 행: note / sentence_role / phrase / clause / other / 미분류 (category null)
 * 칩: annotationId 1개 = 1칩 (split 된 여러 range 라도 1칩)
 */

import "./AnalysisTable.css";

// ---------------------------------------------------------------------------
// 타입
// ---------------------------------------------------------------------------

/**
 * AnnotationChip — 분석표 칩 1개의 데이터.
 * 에디터 외부에서 계산 후 props 로 전달받는다.
 */
export interface AnnotationChip {
  annotationId: string;
  kind: string; // AnnotationKind 문자열 (예: "highlight", "top_label")
  category: string | null;
  colorIndex: number | null;
  labelText: string; // top_label / bottom_label / inline_note 의 text (없으면 "")
  spanText: string; // 본문 span 텍스트 (30자 초과 시 줄임)
}

interface AnalysisTableProps {
  chips: AnnotationChip[];
  onRemove: (annotationId: string) => void;
}

// ---------------------------------------------------------------------------
// 상수
// ---------------------------------------------------------------------------

const CATEGORY_ROWS: Array<{ key: string | null; label: string }> = [
  { key: "note", label: "note" },
  { key: "sentence_role", label: "sentence_role" },
  { key: "phrase", label: "phrase" },
  { key: "clause", label: "clause" },
  { key: "other", label: "other" },
  { key: null, label: "미분류" },
];

/** kind 약어 — 칩 좌측 표시 */
const KIND_ABBR: Record<string, string> = {
  highlight: "H",
  underline: "U",
  top_label: "T",
  bottom_label: "B",
  bracket: "[]",
  arrow: "→",
  inline_note: "=",
};

// ---------------------------------------------------------------------------
// 컴포넌트
// ---------------------------------------------------------------------------

export function AnalysisTable({ chips, onRemove }: AnalysisTableProps) {
  const nonEmpty = CATEGORY_ROWS.filter((row) => chips.some((c) => c.category === row.key));

  if (chips.length === 0) {
    return (
      <div className="analysis-table analysis-table--empty">
        <span className="analysis-table__empty-msg">annotation 없음</span>
      </div>
    );
  }

  return (
    <div className="analysis-table">
      <div className="analysis-table__header">분석표</div>
      {nonEmpty.map((row) => {
        const rowChips = chips.filter((c) => c.category === row.key);
        return (
          <div key={row.key ?? "__null__"} className="analysis-row">
            <div className="analysis-row__label">{row.label}</div>
            <div className="analysis-row__chips">
              {rowChips.map((chip) => (
                <AnnotationChipView key={chip.annotationId} chip={chip} onRemove={onRemove} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 칩 컴포넌트
// ---------------------------------------------------------------------------

interface AnnotationChipViewProps {
  chip: AnnotationChip;
  onRemove: (annotationId: string) => void;
}

function AnnotationChipView({ chip, onRemove }: AnnotationChipViewProps) {
  const abbr = KIND_ABBR[chip.kind] ?? chip.kind.slice(0, 2);
  const colorVar = chip.colorIndex != null ? `var(--anno-color-${chip.colorIndex})` : undefined;

  const displayText = chip.labelText ? `${chip.labelText} ${chip.spanText}` : chip.spanText;

  return (
    <span
      className="anno-chip"
      style={colorVar ? { backgroundColor: colorVar, borderColor: colorVar } : undefined}
    >
      <span className="anno-chip__kind">{abbr}</span>
      <span className="anno-chip__text">{displayText}</span>
      <button
        type="button"
        className="anno-chip__remove"
        title="annotation 삭제"
        onClick={() => onRemove(chip.annotationId)}
      >
        ✕
      </button>
    </span>
  );
}
