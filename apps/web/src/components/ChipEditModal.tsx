/**
 * ChipEditModal — 칩 클릭 시 annotation 수정 모달 (P1-2c follow-up)
 *
 * 칩 kind 별 수정 가능 필드:
 *   - top_label / bottom_label / inline_note: 텍스트 + 색(colorIndex) + (top_label만) 괄호
 *   - highlight: 색(colorIndex)만
 *   - underline: 색 미지원 — 비활성 안내
 *   - bracket: 괄호 스타일 + 색(colorIndex)
 *   - arrow: 수정 불가 — 모달 자체를 열지 않음 (호출자에서 arrow 필터링)
 *
 * 저장 시: 같은 annotationId 의 모든 range 를 수집 → unset → set (attrs 갱신).
 * 삭제 버튼: 기존 칩 ✕ 와 동일 효과 (onRemove 호출).
 *
 * 디자인 패턴: LabelEntryModal 과 동일 (modal-overlay / modal-box CSS 재사용).
 */

import { useEffect, useRef, useState } from "react";
import { HexColorPicker } from "react-colorful";
import type { AnnotationChip } from "./AnalysisTable";
import "./LabelEntryModal.css";
import "./ChipEditModal.css";

// ---------------------------------------------------------------------------
// 타입
// ---------------------------------------------------------------------------

export type BracketEditStyle = "()" | "{}" | "[]";

export interface ChipEditModalProps {
  open: boolean;
  chip: AnnotationChip | null;
  /** bracketStyle — 같은 annotationId 의 bracket mark 에서 가져온 스타일 (top_label 전용) */
  bracketStyle: BracketEditStyle | null;
  onSave: (params: {
    annotationId: string;
    text?: string;
    colorIndex: number | null;
    bracketStyle: BracketEditStyle | null;
  }) => void;
  onRemove: (annotationId: string) => void;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// 상수
// ---------------------------------------------------------------------------

const COLOR_PALETTE: Array<{ index: number; hex: string; label: string }> = [
  { index: 1, hex: "#fef08a", label: "yellow" },
  { index: 2, hex: "#86efac", label: "green" },
  { index: 3, hex: "#93c5fd", label: "blue" },
  { index: 4, hex: "#f9a8d4", label: "pink" },
  { index: 5, hex: "#fdba74", label: "orange" },
  { index: 6, hex: "#c4b5fd", label: "violet" },
  { index: 7, hex: "#6ee7b7", label: "emerald" },
  { index: 8, hex: "#fca5a5", label: "red" },
  { index: 9, hex: "#67e8f9", label: "cyan" },
  { index: 10, hex: "#d9f99d", label: "lime" },
  { index: 11, hex: "#fde68a", label: "amber" },
  { index: 12, hex: "#e9d5ff", label: "purple" },
];

interface BracketOptDef {
  value: BracketEditStyle | "⌜⌟" | "<>";
  label: string;
  disabled: boolean;
  tooltip?: string;
}

const BRACKET_EDIT_OPTS: BracketOptDef[] = [
  { value: "[]", label: "[]", disabled: false },
  { value: "{}", label: "{}", disabled: false },
  { value: "()", label: "()", disabled: false },
  { value: "⌜⌟", label: "⌜⌟", disabled: true, tooltip: "HWPX schema 미지원" },
  { value: "<>", label: "<>", disabled: true, tooltip: "HWPX schema 미지원" },
];

// ---------------------------------------------------------------------------
// 헬퍼
// ---------------------------------------------------------------------------

function kindLabel(kind: string): string {
  const MAP: Record<string, string> = {
    top_label: "구/절 라벨",
    bottom_label: "성분 라벨",
    inline_note: "인라인 노트",
    highlight: "형광펜",
    underline: "밑줄",
    bracket: "괄호",
  };
  return MAP[kind] ?? kind;
}

// ---------------------------------------------------------------------------
// 컴포넌트
// ---------------------------------------------------------------------------

export function ChipEditModal({
  open,
  chip,
  bracketStyle: initialBracketStyle,
  onSave,
  onRemove,
  onClose,
}: ChipEditModalProps) {
  const [text, setText] = useState("");
  const [colorIndex, setColorIndex] = useState<number | null>(1);
  const [bracketStyle, setBracketStyle] = useState<BracketEditStyle | null>(null);
  const [showColorWheel, setShowColorWheel] = useState(false);
  const [pickerDraftHex, setPickerDraftHex] = useState("#fef08a");
  const [customHex, setCustomHex] = useState<string | null>(null);
  const colorWheelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 모달 열릴 때 chip 값으로 초기화
  useEffect(() => {
    if (open && chip) {
      setText(chip.labelText ?? "");
      setColorIndex(chip.colorIndex ?? 1);
      setBracketStyle(initialBracketStyle);
      setShowColorWheel(false);
      setCustomHex(null);
      setPickerDraftHex("#fef08a");
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [open, chip, initialBracketStyle]);

  // 색상 휠 outside click
  useEffect(() => {
    if (!showColorWheel) return;
    function handleOutside(e: MouseEvent) {
      if (colorWheelRef.current && !colorWheelRef.current.contains(e.target as Node)) {
        setShowColorWheel(false);
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [showColorWheel]);

  const handleSubmitRef = useRef<() => void>(() => {});

  // ESC / Enter
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmitRef.current();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open || !chip) return null;

  const kind = chip.kind;
  const hasText = kind === "top_label" || kind === "bottom_label" || kind === "inline_note";
  const hasBracket = kind === "top_label";
  const hasColor = kind !== "underline"; // underline 은 color 미지원
  const isUnderline = kind === "underline";

  function handleSubmit() {
    if (!chip) return;
    onSave({
      annotationId: chip.annotationId,
      text: hasText ? text : undefined,
      colorIndex: customHex ? null : colorIndex,
      bracketStyle,
    });
    onClose();
  }

  handleSubmitRef.current = handleSubmit;

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === e.currentTarget) onClose();
  }

  function handleOverlayKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") onClose();
  }

  function handleDelete() {
    if (!chip) return;
    onRemove(chip.annotationId);
    onClose();
  }

  return (
    <div
      className="modal-overlay"
      onClick={handleOverlayClick}
      onKeyDown={handleOverlayKeyDown}
      role="presentation"
    >
      {/* biome-ignore lint/a11y/useSemanticElements: <dialog> margin:auto 가 flex center 를 깨므로 div 사용 */}
      <div className="modal-box" role="dialog" aria-modal="true" aria-labelledby="chip-edit-title">
        <p id="chip-edit-title" className="modal-title">
          {kindLabel(kind)} 수정
        </p>

        {/* 텍스트 입력 (라벨 종류만) */}
        {hasText && (
          <div className="chip-edit__field">
            <span className="modal-bracket-label">라벨 텍스트</span>
            <input
              ref={inputRef}
              type="text"
              className="modal-label-input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="라벨 텍스트 입력"
            />
          </div>
        )}

        {/* 색상 선택 */}
        {hasColor && (
          <div className="chip-edit__field">
            <span className="modal-bracket-label">색상</span>
            <div className="chip-edit__color-row">
              {COLOR_PALETTE.map((c) => (
                <button
                  key={c.index}
                  type="button"
                  title={`색 ${c.index} (${c.label})`}
                  onClick={() => {
                    setColorIndex(c.index);
                    setCustomHex(null);
                  }}
                  className="chip-edit__color-swatch"
                  style={{
                    backgroundColor: c.hex,
                    outline:
                      colorIndex === c.index && customHex === null
                        ? "2px solid #374151"
                        : "2px solid transparent",
                  }}
                />
              ))}
              {/* 무지개 휠 */}
              <div className="chip-edit__color-wheel-wrap" ref={colorWheelRef}>
                <button
                  type="button"
                  title="자유 색상"
                  onClick={() => {
                    setShowColorWheel((v) => !v);
                    if (!showColorWheel) setPickerDraftHex(customHex ?? "#fef08a");
                  }}
                  className="chip-edit__color-swatch"
                  style={{
                    background: "conic-gradient(red, yellow, lime, cyan, blue, magenta, red)",
                    outline: customHex ? "2px solid #374151" : "2px solid transparent",
                  }}
                  aria-label="자유 색상 휠 열기"
                />
                {showColorWheel && (
                  <div className="chip-edit__color-popover">
                    <HexColorPicker color={pickerDraftHex} onChange={setPickerDraftHex} />
                    <div className="chip-edit__color-popover-row">
                      <span className="chip-edit__color-hex">{pickerDraftHex}</span>
                      <button
                        type="button"
                        className="chip-edit__color-apply-btn"
                        onClick={() => {
                          setCustomHex(pickerDraftHex);
                          setColorIndex(null);
                          setShowColorWheel(false);
                        }}
                      >
                        적용
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* underline: 색 미지원 안내 */}
        {isUnderline && <p className="chip-edit__unsupported">밑줄 색 변경은 현재 미지원입니다.</p>}

        {/* 괄호 스타일 (top_label 만) */}
        {hasBracket && (
          <div className="modal-bracket-section">
            <span className="modal-bracket-label">괄호 스타일</span>
            <div className="modal-bracket-options">
              <button
                type="button"
                className={`modal-bracket-btn${bracketStyle === null ? " selected" : ""}`}
                onClick={() => setBracketStyle(null)}
              >
                없음
              </button>
              {BRACKET_EDIT_OPTS.map((opt) => (
                <button
                  key={opt.label}
                  type="button"
                  className={`modal-bracket-btn${bracketStyle === opt.value ? " selected" : ""}`}
                  disabled={opt.disabled}
                  title={opt.tooltip}
                  onClick={() => {
                    if (!opt.disabled) setBracketStyle(opt.value as BracketEditStyle);
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 버튼 */}
        <div className="chip-edit__actions">
          <button type="button" className="chip-edit__btn-delete" onClick={handleDelete}>
            삭제
          </button>
          <div className="chip-edit__actions-right">
            <button type="button" className="modal-btn-cancel" onClick={onClose}>
              취소
            </button>
            <button type="button" className="modal-btn-submit" onClick={handleSubmit}>
              저장
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
