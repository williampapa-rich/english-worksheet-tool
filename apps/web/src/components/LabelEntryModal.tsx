/**
 * LabelEntryModal — 라벨 텍스트 입력 + 괄호 선택을 통합한 모달 (P1-2c)
 *
 * 외부 라이브러리 없이 div + state 로 자작 (drafts 단계).
 * 괄호 옵션은 phrase / clause 진입 시에만 표시.
 * ⌜⌟ / <> 는 BracketStyle enum 미지원으로 비활성.
 */

import { useEffect, useRef, useState } from "react";
import "./LabelEntryModal.css";

// ---------------------------------------------------------------------------
// 타입
// ---------------------------------------------------------------------------

export type LabelEntryModalKind = "sentence_role" | "phrase" | "clause";

type BracketOption = "()" | "{}" | "[]" | "⌜⌟" | "<>" | null;

export interface LabelEntryModalProps {
  open: boolean;
  entryKind: LabelEntryModalKind;
  onSubmit: (params: { text: string; bracketStyle: "()" | "{}" | "[]" | null }) => void;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// 상수
// ---------------------------------------------------------------------------

const TITLES: Record<LabelEntryModalKind, string> = {
  sentence_role: "성분 라벨 입력",
  phrase: "구 라벨 입력",
  clause: "절 라벨 입력",
};

const PLACEHOLDERS: Record<LabelEntryModalKind, string> = {
  sentence_role: "S, V, O, OC, SC, M",
  phrase: "명사구, 전치사구, to부정사구",
  clause: "부사절, 관계절, 명사절",
};

/** sentence_role preset 버튼 목록. "직접입력" = null (preset 없음 상태) */
const SENTENCE_ROLE_PRESETS: Array<{ label: string; value: string | null }> = [
  { label: "S", value: "S" },
  { label: "V", value: "V" },
  { label: "O", value: "O" },
  { label: "OC", value: "OC" },
  { label: "SC", value: "SC" },
  { label: "M", value: "M" },
  { label: "직접입력", value: null },
];

interface BracketOptionDef {
  value: BracketOption;
  label: string;
  disabled: boolean;
  tooltip?: string;
}

const BRACKET_OPTIONS: BracketOptionDef[] = [
  { value: null, label: "없음", disabled: false },
  { value: "[]", label: "[]", disabled: false },
  { value: "{}", label: "{}", disabled: false },
  { value: "()", label: "()", disabled: false },
  {
    value: "⌜⌟",
    label: "⌜⌟",
    disabled: true,
    tooltip: "HWPX schema 미지원 — P1-8b 후 활성",
  },
  {
    value: "<>",
    label: "<>",
    disabled: true,
    tooltip: "HWPX schema 미지원 — P1-8b 후 활성",
  },
];

// ---------------------------------------------------------------------------
// 컴포넌트
// ---------------------------------------------------------------------------

export function LabelEntryModal({ open, entryKind, onSubmit, onClose }: LabelEntryModalProps) {
  const [text, setText] = useState("");
  const [bracketOption, setBracketOption] = useState<BracketOption>(null);
  const [inputError, setInputError] = useState(false);
  /**
   * selectedPreset:
   *   - null  → 직접입력 모드 (기본)
   *   - string → 해당 preset 선택됨, input disabled
   */
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const isSentenceRole = entryKind === "sentence_role";

  // 모달 열릴 때 상태 초기화 + autoFocus
  useEffect(() => {
    if (open) {
      setText("");
      setBracketOption(null);
      setInputError(false);
      setSelectedPreset(null);
      // 다음 프레임에 포커스 — 모달 DOM 마운트 후
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [open]);

  // handleSubmit 을 ref 로 보관 — useEffect deps 순환 회피
  const handleSubmitRef = useRef<() => void>(() => {});

  // ESC / Enter 단축키
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "Enter") {
        e.preventDefault();
        handleSubmitRef.current();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  const showBracket = entryKind === "phrase" || entryKind === "clause";

  /** 실제 제출 텍스트 — preset 선택 시 preset 값, 직접입력 모드면 textarea 값 */
  function resolveText(): string {
    if (isSentenceRole && selectedPreset !== null) return selectedPreset;
    return text;
  }

  function handleSubmit() {
    const resolved = resolveText();
    if (!resolved.trim()) {
      setInputError(true);
      inputRef.current?.focus();
      return;
    }
    // bracketOption 이 disabled 값이면 null 로 강제 (방어)
    const safeBracket =
      bracketOption === "()" || bracketOption === "{}" || bracketOption === "[]"
        ? bracketOption
        : null;
    onSubmit({ text: resolved.trim(), bracketStyle: safeBracket });
    onClose();
  }

  // ref 업데이트 — 최신 text/selectedPreset/bracketOption 캡처
  handleSubmitRef.current = handleSubmit;

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    // 모달 박스 외부 클릭 시 닫기
    if (e.target === e.currentTarget) onClose();
  }

  function handleOverlayKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    // overlay 레벨 키보드 이벤트 — 접근성 (실제 ESC/Enter 는 window listener 처리)
    if (e.key === "Escape") onClose();
  }

  function handlePresetClick(presetValue: string | null) {
    setSelectedPreset(presetValue);
    setInputError(false);
    if (presetValue === null) {
      // 직접입력 모드로 전환 — input 활성 + focus
      setText("");
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }

  /** input disabled 여부 — sentence_role 에서 preset 선택 시 */
  const isInputDisabled = isSentenceRole && selectedPreset !== null;

  if (!open) return null;

  return (
    <div
      className="modal-overlay"
      onClick={handleOverlayClick}
      onKeyDown={handleOverlayKeyDown}
      role="presentation"
    >
      <dialog className="modal-box" open aria-labelledby="modal-title">
        <p id="modal-title" className="modal-title">
          {TITLES[entryKind]}
        </p>

        {/* sentence_role 전용 preset 버튼 그룹 */}
        {isSentenceRole && (
          <div className="modal-preset-section">
            <span className="modal-preset-label">빠른 선택</span>
            <div className="modal-preset-options">
              {SENTENCE_ROLE_PRESETS.map((p) => {
                const isSelected =
                  p.value === null ? selectedPreset === null : selectedPreset === p.value;
                return (
                  <button
                    key={p.label}
                    type="button"
                    className={`modal-preset-btn${isSelected ? " selected" : ""}`}
                    onClick={() => handlePresetClick(p.value)}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* 라벨 텍스트 입력 — sentence_role preset 선택 시 disabled */}
        <input
          ref={inputRef}
          type="text"
          className={`modal-label-input${inputError ? " error" : ""}`}
          placeholder={
            isSentenceRole && selectedPreset !== null ? selectedPreset : PLACEHOLDERS[entryKind]
          }
          value={isSentenceRole && selectedPreset !== null ? selectedPreset : text}
          disabled={isInputDisabled}
          onChange={(e) => {
            if (isInputDisabled) return;
            setText(e.target.value);
            if (inputError) setInputError(false);
          }}
        />

        {/* 괄호 선택 — phrase / clause 만 */}
        {showBracket && (
          <div className="modal-bracket-section">
            <span className="modal-bracket-label">괄호 스타일</span>
            <div className="modal-bracket-options">
              {BRACKET_OPTIONS.map((opt) => (
                <button
                  key={opt.label}
                  type="button"
                  className={`modal-bracket-btn${bracketOption === opt.value ? " selected" : ""}`}
                  disabled={opt.disabled}
                  title={opt.tooltip}
                  onClick={() => setBracketOption(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 버튼 */}
        <div className="modal-actions">
          <button type="button" className="modal-btn-cancel" onClick={onClose}>
            취소
          </button>
          <button type="button" className="modal-btn-submit" onClick={handleSubmit}>
            확인
          </button>
        </div>
      </dialog>
    </div>
  );
}
