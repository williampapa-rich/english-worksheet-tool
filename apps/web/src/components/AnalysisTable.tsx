/**
 * AnalysisTable — 분석표 컴포넌트 (P1-2c, C-2b)
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
 *
 * C-2b 변경:
 *   - 성분 행에 SentenceRolePresetBar 추가 (preset 버튼 윗줄 / 칩 아랫줄)
 *   - sentenceRolePresets / onSentenceRolePresetClick / onSentenceRolePresetAdd / onSentenceRolePresetRemove props 추가
 *   - highlight kind 칩: colorIndex 외에 mark.attrs.color hex 를 직접 적용 (자유색상 동기화)
 *     → AnnotationChip.highlightHex 필드 추가 (buildChips 에서 채움)
 */

import { useState } from "react";
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
  /** 같은 annotationId 에 bracket mark 가 있을 때 해당 스타일 (top_label 전용). P1-10c: ⌜⌟ / <> 추가 */
  bracketStyle?: "()" | "{}" | "[]" | "⌜⌟" | "<>" | null;
  /**
   * C-2b: highlight kind 전용 — mark.attrs.color hex 를 직접 전달.
   * 자유색상 picker 로 설정한 hex 가 colorIndex 팔레트 매핑 없이 칩에 바로 반영됨.
   * highlight 외 kind 에서는 undefined.
   */
  highlightHex?: string | null;
}

/**
 * LabelEntryKind — 진입 버튼 또는 툴바 버튼으로 생성되는 mark 종류.
 *
 * P1-followup-ng-fixes NG 2: note top/bottom 추가 (툴바 자유 메모 버튼).
 */
export type LabelEntryKind =
  | { markKind: "bottom_label"; category: "sentence_role" }
  | { markKind: "top_label"; category: "phrase" }
  | { markKind: "top_label"; category: "clause" }
  | { markKind: "top_label"; category: "note" }
  | { markKind: "bottom_label"; category: "note" };

interface AnalysisTableProps {
  chips: AnnotationChip[];
  onRemove: (annotationId: string) => void;
  /** 진입 버튼 클릭 — EditorPoc 에서 selection 확인 후 mark 적용 */
  onLabelEntry: (entry: LabelEntryKind) => void;
  /** 칩 클릭 — 수정 모달 열기 (arrow 제외) */
  onChipClick?: (chip: AnnotationChip) => void;

  // C-2b: 성분 행 preset 관련 props
  /** 성분 preset 목록 (예: ["S", "V", "O", "OC", "SC"]). undefined 이면 preset bar 미표시. */
  sentenceRolePresets?: string[];
  /** preset 버튼 클릭 — 해당 텍스트로 성분 라벨 진입 모달 트리거 */
  onSentenceRolePresetClick?: (presetLabel: string) => void;
  /** 커스텀 preset 추가 */
  onSentenceRolePresetAdd?: (label: string) => void;
  /** 커스텀 preset 삭제 */
  onSentenceRolePresetRemove?: (label: string) => void;
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

export function AnalysisTable({
  chips,
  onRemove,
  onLabelEntry,
  onChipClick,
  sentenceRolePresets,
  onSentenceRolePresetClick,
  onSentenceRolePresetAdd,
  onSentenceRolePresetRemove,
}: AnalysisTableProps) {
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
            {/* 우측: 성분 행이면 preset bar (윗줄) + 칩 (아랫줄), 나머지 행은 칩만 */}
            <div className="analysis-row__right">
              {row.key === "sentence_role" && sentenceRolePresets !== undefined && (
                <SentenceRolePresetBar
                  presets={sentenceRolePresets}
                  onPresetClick={onSentenceRolePresetClick}
                  onPresetAdd={onSentenceRolePresetAdd}
                  onPresetRemove={onSentenceRolePresetRemove}
                />
              )}
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
// 성분 preset bar (C-2b)
// ---------------------------------------------------------------------------

interface SentenceRolePresetBarProps {
  presets: string[];
  onPresetClick?: (label: string) => void;
  onPresetAdd?: (label: string) => void;
  onPresetRemove?: (label: string) => void;
}

/**
 * SentenceRolePresetBar — 성분 행 윗줄에 표시되는 preset 버튼 영역.
 *
 * - preset 버튼: 클릭 시 onPresetClick(label) 호출 → EditorPoc 에서 모달 트리거
 * - "+" 버튼: 커스텀 라벨 입력 후 onPresetAdd 호출 → 목록 끝에 추가
 * - "x" 버튼 (각 preset 우측): onPresetRemove 호출 → 해당 라벨 삭제
 */
function SentenceRolePresetBar({
  presets,
  onPresetClick,
  onPresetAdd,
  onPresetRemove,
}: SentenceRolePresetBarProps) {
  const [addMode, setAddMode] = useState(false);
  const [draft, setDraft] = useState("");

  function handleAddConfirm() {
    const label = draft.trim();
    if (label && label.length <= 16) {
      onPresetAdd?.(label);
    }
    setDraft("");
    setAddMode(false);
  }

  function handleAddKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddConfirm();
    } else if (e.key === "Escape") {
      setDraft("");
      setAddMode(false);
    }
  }

  return (
    <div className="preset-bar">
      {presets.map((label) => (
        <span key={label} className="preset-bar__item">
          <button
            type="button"
            className="preset-bar__btn"
            onMouseDown={(e) => e.preventDefault()} // ProseMirror selection 보존
            onClick={() => onPresetClick?.(label)}
          >
            {label}
          </button>
          {onPresetRemove && (
            <button
              type="button"
              className="preset-bar__remove"
              title={`${label} preset 삭제`}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => onPresetRemove(label)}
            >
              ✕
            </button>
          )}
        </span>
      ))}
      {/* 커스텀 추가 */}
      {addMode ? (
        <span className="preset-bar__add-input-wrap">
          <input
            // biome-ignore lint/a11y/noAutofocus: 인라인 입력 포커스 의도적
            autoFocus
            type="text"
            className="preset-bar__add-input"
            placeholder="라벨 (최대 16자)"
            value={draft}
            maxLength={16}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleAddKeyDown}
            onBlur={handleAddConfirm}
          />
        </span>
      ) : (
        onPresetAdd && (
          <button
            type="button"
            className="preset-bar__add-btn"
            title="커스텀 preset 추가"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => setAddMode(true)}
          >
            +
          </button>
        )
      )}
    </div>
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

  // C-2b: highlight 자유색상 동기화 (PM 결정 1 — 구현 방식 C)
  // highlightHex 가 있으면 (자유색상 포함) 직접 hex 를 배경색으로 적용.
  // highlightHex 없으면 colorIndex CSS 변수 fallback.
  const resolveHighlightBg = (): string | undefined => {
    if (chip.kind !== "highlight") return undefined;
    if (chip.highlightHex) return chip.highlightHex;
    if (chip.colorIndex != null) return `var(--anno-color-${chip.colorIndex})`;
    return undefined;
  };

  const colorVar = chip.colorIndex != null ? `var(--anno-color-${chip.colorIndex})` : undefined;

  // arrow 는 수정 불가 — 칩 클릭 핸들러 없음
  const isEditable = chip.kind !== "arrow";

  // NG 4: underline 칩은 배경색 gray-200 고정 (밑줄 mark 자체는 색상 없음 — black 고정).
  // inline_note 도 동일 정책 (사용자 요청 2026-05-08) — note mark 자체는 색상 없이
  // 검정 small-text 렌더이므로 칩도 회색이 자연스러움.
  // DB colorIndex 저장은 그대로 유지, UI 표시만 회색 강제.
  const highlightBg = resolveHighlightBg();
  const isGrayKind = chip.kind === "underline" || chip.kind === "inline_note";
  const chipStyle = isGrayKind
    ? { backgroundColor: "#e5e7eb", borderColor: "#d1d5db" }
    : chip.kind === "highlight" && highlightBg
      ? { backgroundColor: highlightBg, borderColor: highlightBg }
      : colorVar
        ? { backgroundColor: colorVar, borderColor: colorVar }
        : undefined;

  return (
    <span
      className={`anno-chip${isEditable ? " anno-chip--clickable" : ""}`}
      style={chipStyle}
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
