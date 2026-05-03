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
  const inputRef = useRef<HTMLInputElement>(null);

  // 모달 열릴 때 상태 초기화 + autoFocus
  useEffect(() => {
    if (open) {
      setText("");
      setBracketOption(null);
      setInputError(false);
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

  function handleSubmit() {
    if (!text.trim()) {
      setInputError(true);
      inputRef.current?.focus();
      return;
    }
    // bracketOption 이 disabled 값이면 null 로 강제 (방어)
    const safeBracket =
      bracketOption === "()" || bracketOption === "{}" || bracketOption === "[]"
        ? bracketOption
        : null;
    onSubmit({ text: text.trim(), bracketStyle: safeBracket });
    onClose();
  }

  // ref 업데이트 — 최신 text/bracketOption 캡처
  handleSubmitRef.current = handleSubmit;

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    // 모달 박스 외부 클릭 시 닫기
    if (e.target === e.currentTarget) onClose();
  }

  function handleOverlayKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    // overlay 레벨 키보드 이벤트 — 접근성 (실제 ESC/Enter 는 window listener 처리)
    if (e.key === "Escape") onClose();
  }

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

        {/* 라벨 텍스트 입력 */}
        <input
          ref={inputRef}
          type="text"
          className={`modal-label-input${inputError ? " error" : ""}`}
          placeholder={PLACEHOLDERS[entryKind]}
          value={text}
          onChange={(e) => {
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
