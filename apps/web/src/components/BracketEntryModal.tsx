/**
 * BracketEntryModal — 툴바 괄호 버튼 클릭 시 열리는 모달 (P1-2c follow-up)
 *
 * 옵션 5개: [] / {} / () / ⌜⌟(disabled) / <>(disabled)
 * 디폴트 선택: ()
 * ESC = 취소, Enter = 확인.
 * 디자인: LabelEntryModal 과 동일 패턴 (modal-overlay / modal-box).
 */

import { useEffect, useRef, useState } from "react";
import "./LabelEntryModal.css";

// ---------------------------------------------------------------------------
// 타입
// ---------------------------------------------------------------------------

export type BracketStyleOption = "()" | "{}" | "[]" | "⌜⌟" | "<>";

export interface BracketEntryModalProps {
  open: boolean;
  onSubmit: (style: BracketStyleOption) => void;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// 상수
// ---------------------------------------------------------------------------

interface BracketOptDef {
  value: BracketStyleOption;
  label: string;
  disabled: boolean;
  tooltip?: string;
}

// P1-10c: ⌜⌟ / <> 활성화 (schema + HWPX Unicode inline run 지원 확인 완료)
const BRACKET_OPTS: BracketOptDef[] = [
  { value: "[]", label: "[]", disabled: false },
  { value: "{}", label: "{}", disabled: false },
  { value: "()", label: "()", disabled: false },
  { value: "⌜⌟", label: "⌜⌟", disabled: false },
  { value: "<>", label: "<>", disabled: false },
];

// ---------------------------------------------------------------------------
// 컴포넌트
// ---------------------------------------------------------------------------

export function BracketEntryModal({ open, onSubmit, onClose }: BracketEntryModalProps) {
  const [selected, setSelected] = useState<BracketStyleOption>("()");

  const handleSubmitRef = useRef<() => void>(() => {});

  // 모달 열릴 때 기본값 초기화
  useEffect(() => {
    if (open) {
      setSelected("()");
    }
  }, [open]);

  // ESC / Enter 키보드 단축키
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

  function handleSubmit() {
    onSubmit(selected);
    onClose();
  }

  handleSubmitRef.current = handleSubmit;

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === e.currentTarget) onClose();
  }

  function handleOverlayKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
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
      {/* biome-ignore lint/a11y/useSemanticElements: <dialog> 가 정중앙 정렬을 강제로 깨서 div 사용 */}
      <div className="modal-box" role="dialog" aria-modal="true" aria-labelledby="bkt-title">
        <p id="bkt-title" className="modal-title">
          괄호 스타일 선택
        </p>

        <div className="modal-bracket-section">
          <span className="modal-bracket-label">스타일</span>
          <div className="modal-bracket-options">
            {BRACKET_OPTS.map((opt) => (
              <button
                key={opt.label}
                type="button"
                className={`modal-bracket-btn${selected === opt.value ? " selected" : ""}`}
                disabled={opt.disabled}
                title={opt.tooltip}
                onClick={() => {
                  if (!opt.disabled) {
                    setSelected(opt.value as BracketStyleOption);
                  }
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div className="modal-actions">
          <button type="button" className="modal-btn-cancel" onClick={onClose}>
            취소
          </button>
          <button type="button" className="modal-btn-submit" onClick={handleSubmit}>
            확인
          </button>
        </div>
      </div>
    </div>
  );
}
