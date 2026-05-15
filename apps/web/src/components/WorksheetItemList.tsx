/**
 * WorksheetItemList — Worksheet 의 items 목록 + 추가/삭제/순서 변경 UI (Stage E2-3e).
 *
 * WorksheetEditPage 의 좌측 상단 아이템 탭을 컴포넌트로 분리. + 버튼은 새 지문
 * 추가 모달, × 버튼은 즉시 삭제 (confirm 없음 — 와이프 검수 후 추가 검토),
 * 위/아래 화살표는 인접 item 과 order swap PATCH.
 *
 * 순서 변경: 드래그 라이브러리 도입 대신 위/아래 버튼 (NRTW — 1차 검수용).
 * 와이프 피드백 후 react-dnd / dnd-kit 도입 검토.
 *
 * order 충돌 정책: 백엔드 PM 결정 (worksheets.py §501) — 같은 order 가진 items
 * 가 둘 이상이어도 저장 허용. 본 컴포넌트는 인접 swap 만 하므로 충돌 없음.
 */
import { type ReactElement, useState } from "react";
import {
  type Worksheet,
  type WorksheetItem,
  addWorksheetItem,
  deleteWorksheetItem,
  extractPassageText,
  patchWorksheetItem,
} from "../lib/api";

export function WorksheetItemList({
  worksheet,
  activeItemId,
  onSelect,
  onChanged,
}: {
  worksheet: Worksheet;
  activeItemId: string | null;
  onSelect: (itemId: string) => void;
  /** items 변경 후 부모가 worksheet refetch 하도록 통지. */
  onChanged: () => void;
}): ReactElement {
  const [showAddModal, setShowAddModal] = useState(false);
  const [pendingItemId, setPendingItemId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // order 오름차순으로 정렬해서 표시 — 같은 order 면 id 로 안정 정렬.
  const sortedItems = [...worksheet.items].sort((a, b) => {
    if (a.order !== b.order) return a.order - b.order;
    return a.id.localeCompare(b.id);
  });

  async function handleDelete(itemId: string): Promise<void> {
    if (!confirm("이 아이템을 삭제할까요? 되돌릴 수 없습니다.")) return;
    setPendingItemId(itemId);
    setError(null);
    try {
      await deleteWorksheetItem(worksheet.id, itemId);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingItemId(null);
    }
  }

  async function handleMove(itemId: string, direction: "up" | "down"): Promise<void> {
    const idx = sortedItems.findIndex((it) => it.id === itemId);
    if (idx < 0) return;
    const swapIdx = direction === "up" ? idx - 1 : idx + 1;
    if (swapIdx < 0 || swapIdx >= sortedItems.length) return;

    const current = sortedItems[idx];
    const neighbor = sortedItems[swapIdx];
    if (!current || !neighbor) return;

    setPendingItemId(itemId);
    setError(null);
    try {
      // 두 item 의 order 를 교환. 같은 order 충돌 허용 정책이지만 swap 은 두 PATCH 가
      // 끝나면 항상 다른 값 — 일시적 동일 order 는 허용.
      await patchWorksheetItem(worksheet.id, current.id, { order: neighbor.order });
      await patchWorksheetItem(worksheet.id, neighbor.id, { order: current.order });
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingItemId(null);
    }
  }

  return (
    <>
      <div className="bg-white border-b border-gray-200 px-4 flex items-center gap-1 shrink-0 overflow-x-auto">
        {sortedItems.map((item, idx) => {
          const active = item.id === activeItemId;
          const pending = pendingItemId === item.id;
          const isFirst = idx === 0;
          const isLast = idx === sortedItems.length - 1;
          return (
            <ItemTab
              key={item.id}
              item={item}
              order={idx + 1}
              active={active}
              pending={pending}
              isFirst={isFirst}
              isLast={isLast}
              onSelect={() => onSelect(item.id)}
              onMoveUp={() => handleMove(item.id, "up")}
              onMoveDown={() => handleMove(item.id, "down")}
              onDelete={() => handleDelete(item.id)}
            />
          );
        })}

        <button
          type="button"
          onClick={() => setShowAddModal(true)}
          className="text-xs px-3 py-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors whitespace-nowrap shrink-0"
          title="아이템 추가"
        >
          + 추가
        </button>

        {error && (
          <div className="text-xs text-red-600 ml-auto pl-2 truncate max-w-xs" title={error}>
            {error}
          </div>
        )}
      </div>

      {showAddModal && (
        <AddItemModal
          worksheetId={worksheet.id}
          nextOrder={sortedItems.length}
          onClose={() => setShowAddModal(false)}
          onAdded={() => {
            setShowAddModal(false);
            onChanged();
          }}
        />
      )}
    </>
  );
}

// ─── ItemTab — 1개 탭 (선택 / 위·아래 / 삭제 컨트롤 포함) ────────────────────

function ItemTab({
  item,
  order,
  active,
  pending,
  isFirst,
  isLast,
  onSelect,
  onMoveUp,
  onMoveDown,
  onDelete,
}: {
  item: WorksheetItem;
  order: number;
  active: boolean;
  pending: boolean;
  isFirst: boolean;
  isLast: boolean;
  onSelect: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDelete: () => void;
}): ReactElement {
  return (
    <div
      className={`flex items-center border-b-2 transition-colors shrink-0 ${
        active ? "border-blue-500" : "border-transparent"
      } ${pending ? "opacity-50" : ""}`}
    >
      <button
        type="button"
        onClick={onSelect}
        className={`text-xs px-3 py-2 transition-colors whitespace-nowrap font-mono ${
          active ? "text-blue-600" : "text-gray-500 hover:text-gray-700"
        }`}
      >
        {order}. {item.label ?? `${item.passage_id.slice(0, 8)}…`}
      </button>
      {active && (
        <div className="flex items-center gap-0.5 pr-1">
          <IconButton
            onClick={onMoveUp}
            disabled={isFirst || pending}
            title="앞으로 이동"
            label="↑"
          />
          <IconButton
            onClick={onMoveDown}
            disabled={isLast || pending}
            title="뒤로 이동"
            label="↓"
          />
          <IconButton onClick={onDelete} disabled={pending} title="삭제" label="×" danger />
        </div>
      )}
    </div>
  );
}

function IconButton({
  onClick,
  disabled,
  title,
  label,
  danger,
}: {
  onClick: () => void;
  disabled: boolean;
  title: string;
  label: string;
  danger?: boolean;
}): ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`w-6 h-6 flex items-center justify-center text-xs rounded transition-colors ${
        disabled
          ? "text-gray-300 cursor-not-allowed"
          : danger
            ? "text-gray-400 hover:text-red-600 hover:bg-red-50"
            : "text-gray-400 hover:text-gray-700 hover:bg-gray-100"
      }`}
    >
      {label}
    </button>
  );
}

// ─── AddItemModal — 새 지문 텍스트 입력 → extract → addItem ──────────────────

function AddItemModal({
  worksheetId,
  nextOrder,
  onClose,
  onAdded,
}: {
  worksheetId: string;
  /** 추가할 item 의 order (현재 items 개수 = 마지막 자리). */
  nextOrder: number;
  onClose: () => void;
  onAdded: () => void;
}): ReactElement {
  const [body, setBody] = useState("");
  const [label, setLabel] = useState("");
  const [includeTranslation, setIncludeTranslation] = useState(true);
  const [includeVocabulary, setIncludeVocabulary] = useState(true);
  const [includeSyntax, setIncludeSyntax] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!body.trim()) {
      setError("지문을 입력해주세요.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const results = await extractPassageText(body);
      const first = results[0];
      if (!first) throw new Error("extract 결과가 비어있습니다.");
      await addWorksheetItem(worksheetId, {
        passage_id: first.passage.id,
        order: nextOrder,
        label: label.trim() || null,
        include_translation: includeTranslation,
        include_vocabulary: includeVocabulary,
        include_syntax_annotations: includeSyntax,
      });
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={onClose}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      role="presentation"
    >
      <div
        className="bg-white rounded-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
        // biome-ignore lint/a11y/useSemanticElements: <dialog> 가 정중앙 정렬을 강제로 깨서 div 사용 (다른 모달과 동일 패턴)
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-900">아이템 추가</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-xl leading-none"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="add-item-body" className="block text-sm font-medium text-gray-700 mb-1">
              영어 지문 <span className="text-red-500">*</span>
            </label>
            <textarea
              id="add-item-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={8}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="추가할 영어 지문을 붙여넣으세요."
              disabled={submitting}
            />
          </div>

          <div>
            <label
              htmlFor="add-item-label"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              아이템 라벨 (선택)
            </label>
            <input
              id="add-item-label"
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="예: 관계절이 포함된 문장"
              disabled={submitting}
            />
          </div>

          <fieldset className="border border-gray-200 rounded-md p-3">
            <legend className="text-xs font-medium text-gray-600 px-1">미리보기 포함 옵션</legend>
            <div className="space-y-1.5 mt-1">
              <Checkbox
                label="한글 해석"
                checked={includeTranslation}
                onChange={setIncludeTranslation}
                disabled={submitting}
              />
              <Checkbox
                label="어휘 박스"
                checked={includeVocabulary}
                onChange={setIncludeVocabulary}
                disabled={submitting}
              />
              <Checkbox
                label="구문분석 마크"
                checked={includeSyntax}
                onChange={setIncludeSyntax}
                disabled={submitting}
              />
            </div>
          </fieldset>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-3 text-sm">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md transition-colors disabled:opacity-50"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={submitting || !body.trim()}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? "추가 중…" : "추가"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Checkbox({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled: boolean;
}): ReactElement {
  return (
    <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="rounded border-gray-300"
      />
      {label}
    </label>
  );
}
