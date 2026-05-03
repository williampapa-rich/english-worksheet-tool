/**
 * AnalysisTable — 분석표 컴포넌트 (P1-2c)
 *
 * 5행 고정 (메모 / 성분 / 구 / 절 / 기타) 으로 annotation 을 카테고리별로 표시한다.
 * 행 좌측: 카테고리 라벨 + (해당 시) 진입 버튼
 * 행 우측: annotationId 1개 = 1칩
 *
 * 변경 (vs P1-2b):
 *   - CATEGORY_ROWS 를 5행 고정으로 재정의 (미분류 행 제거)
 *   - 기타(other) 행은 chips 없을 때 hide
 *   - 나머지 4행 (메모/성분/구/절) 은 chips 없어도 항상 표시 (진입 버튼이 있으므로)
 *   - 행 좌측에 진입 버튼 (성분/구/절) 또는 안내 텍스트 (메모) 추가
 *   - 칩 좌측: top_label/bottom_label/inline_note 는 text attrs 표기, 나머지 kind 약어
 *   - onLabelEntry 콜백 — 진입 버튼 클릭 시 EditorPoc 에서 mark 적용
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
  /** 같은 annotationId 에 bracket mark 가 있을 때 해당 스타일 (top_label 전용) */
  bracketStyle?: "()" | "{}" | "[]" | null;
}

/**
 * LabelEntryKind — 진입 버튼으로 생성되는 mark 종류
 */
export type LabelEntryKind =
  | { markKind: "bottom_label"; category: "sentence_role" }
  | { markKind: "top_label"; category: "phrase" }
  | { markKind: "top_label"; category: "clause" };

interface AnalysisTableProps {
  chips: AnnotationChip[];
  onRemove: (annotationId: string) => void;
  /** 진입 버튼 클릭 — EditorPoc 에서 selection 확인 후 mark 적용 */
  onLabelEntry: (entry: LabelEntryKind) => void;
  /** 칩 클릭 — 수정 모달 열기 (arrow 제외) */
  onChipClick?: (chip: AnnotationChip) => void;
}

// ---------------------------------------------------------------------------
// 상수
// ---------------------------------------------------------------------------

interface CategoryRowDef {
  key: string;
  label: string;
  /** true 이면 chips 없어도 항상 표시 */
  alwaysShow: boolean;
  entryButton: { label: string; entry: LabelEntryKind } | null;
  /** 진입 버튼 없는 행의 안내 텍스트 */
  hint: string | null;
}

const CATEGORY_ROWS: CategoryRowDef[] = [
  {
    key: "note",
    label: "메모",
    alwaysShow: true,
    entryButton: null,
    hint: "툴바 5종 자동 매핑",
  },
  {
    key: "sentence_role",
    label: "성분",
    alwaysShow: true,
    entryButton: {
      label: "성분 +",
      entry: { markKind: "bottom_label", category: "sentence_role" },
    },
    hint: null,
  },
  {
    key: "phrase",
    label: "구",
    alwaysShow: true,
    entryButton: {
      label: "구 +",
      entry: { markKind: "top_label", category: "phrase" },
    },
    hint: null,
  },
  {
    key: "clause",
    label: "절",
    alwaysShow: true,
    entryButton: {
      label: "절 +",
      entry: { markKind: "top_label", category: "clause" },
    },
    hint: null,
  },
  {
    key: "other",
    label: "기타",
    alwaysShow: false, // chips 없으면 hide
    entryButton: null,
    hint: null,
  },
];

/** kind 약어 — 라벨 없는 칩에 사용 */
const KIND_ABBR: Record<string, string> = {
  highlight: "H",
  underline: "U",
  bracket: "[]",
  arrow: "→",
};

// ---------------------------------------------------------------------------
// 컴포넌트
// ---------------------------------------------------------------------------

export function AnalysisTable({ chips, onRemove, onLabelEntry, onChipClick }: AnalysisTableProps) {
  // 표시할 행: alwaysShow 이거나 chips 가 있는 행
  const visibleRows = CATEGORY_ROWS.filter(
    (row) => row.alwaysShow || chips.some((c) => c.category === row.key)
  );

  return (
    <div className="analysis-table">
      <div className="analysis-table__header">분석표</div>
      {visibleRows.map((row) => {
        const rowChips = chips.filter((c) => c.category === row.key);
        return (
          <div key={row.key} className="analysis-row">
            {/* 좌측: 라벨 + 진입 버튼 or 힌트 (힌트는 chips 없을 때만 표시) */}
            <div className="analysis-row__left">
              <span className="analysis-row__label">{row.label}</span>
              {row.entryButton && (
                <EntryButton
                  label={row.entryButton.label}
                  entry={row.entryButton.entry}
                  onLabelEntry={onLabelEntry}
                />
              )}
              {row.hint && rowChips.length === 0 && (
                <span className="analysis-row__hint">{row.hint}</span>
              )}
            </div>
            {/* 우측: 칩 목록 */}
            <div className="analysis-row__chips">
              {rowChips.map((chip) => (
                <AnnotationChipView
                  key={chip.annotationId}
                  chip={chip}
                  onRemove={onRemove}
                  onChipClick={onChipClick}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 진입 버튼
// ---------------------------------------------------------------------------

interface EntryButtonProps {
  label: string;
  entry: LabelEntryKind;
  onLabelEntry: (entry: LabelEntryKind) => void;
}

function EntryButton({ label, entry, onLabelEntry }: EntryButtonProps) {
  return (
    <button
      type="button"
      className="analysis-row__entry-btn"
      onMouseDown={(e) => {
        // mousedown 시점에 preventDefault → ProseMirror selection 보존
        e.preventDefault();
      }}
      onClick={(e) => {
        e.preventDefault();
        onLabelEntry(entry);
      }}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// 칩 컴포넌트
// ---------------------------------------------------------------------------

interface AnnotationChipViewProps {
  chip: AnnotationChip;
  onRemove: (annotationId: string) => void;
  onChipClick?: (chip: AnnotationChip) => void;
}

function AnnotationChipView({ chip, onRemove, onChipClick }: AnnotationChipViewProps) {
  // 좌측 표기: top_label / bottom_label / inline_note 는 labelText, 그 외 kind 약어
  const hasLabel =
    (chip.kind === "top_label" || chip.kind === "bottom_label" || chip.kind === "inline_note") &&
    chip.labelText !== "";

  const leftLabel = hasLabel
    ? chip.labelText
    : (KIND_ABBR[chip.kind] ?? chip.kind.slice(0, 2).toUpperCase());

  const colorVar = chip.colorIndex != null ? `var(--anno-color-${chip.colorIndex})` : undefined;

  // arrow 는 수정 불가 — 칩 클릭 핸들러 없음
  const isEditable = chip.kind !== "arrow";

  return (
    <span
      className={`anno-chip${isEditable ? " anno-chip--clickable" : ""}`}
      style={colorVar ? { backgroundColor: colorVar, borderColor: colorVar } : undefined}
      onClick={isEditable && onChipClick ? () => onChipClick(chip) : undefined}
      role={isEditable && onChipClick ? "button" : undefined}
      tabIndex={isEditable && onChipClick ? 0 : undefined}
      onKeyDown={
        isEditable && onChipClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onChipClick(chip);
              }
            }
          : undefined
      }
    >
      <span className="anno-chip__kind">{leftLabel}</span>
      <span className="anno-chip__text">{chip.spanText}</span>
      <button
        type="button"
        className="anno-chip__remove"
        title="annotation 삭제"
        onClick={(e) => {
          // x 클릭이 칩 클릭 이벤트(수정 모달)로 전파되지 않도록
          e.stopPropagation();
          onRemove(chip.annotationId);
        }}
      >
        ✕
      </button>
    </span>
  );
}
