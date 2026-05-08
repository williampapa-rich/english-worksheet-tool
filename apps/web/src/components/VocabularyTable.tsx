/**
 * VocabularyTable — Vocabulary 행 인라인 편집 + "+" 추가 + 삭제 (Stage E2-3b).
 *
 * ADR-0015 D6 결정 (b) "+" 버튼 패턴 — 빈 행 명시 추가.
 * ADR-0015 D3 결정 (b) — 모든 항목 (LLM/USER) 삭제 허용.
 *
 * 동작:
 *   - 행 편집: word / pos / meaning_ko / level_label 을 인라인 input 으로.
 *     blur 시 patchVocabulary 호출. backend 가 user_edited=true 갱신.
 *   - "+" 버튼: word / meaning_ko 입력 폼 인라인 노출 → 저장 시 addVocabulary.
 *   - 삭제: 행 끝 "×" 버튼 → 확인 후 deleteVocabulary.
 *
 * 외부 props.vocabulary 와 onChange(updated[]) 콜백 — 부모가 vocabulary list
 * 상태를 소유 (다른 컴포넌트가 같은 데이터 참조 가능성).
 */
import { type ReactElement, useEffect, useRef, useState } from "react";
import {
  type Vocabulary,
  type VocabularyEditInput,
  addVocabulary,
  deleteVocabulary,
  patchVocabulary,
} from "../lib/api";

interface Props {
  passageId: string;
  vocabulary: Vocabulary[];
  onChange: (updated: Vocabulary[]) => void;
}

export function VocabularyTable({ passageId, vocabulary, onChange }: Props): ReactElement {
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [pendingRowId, setPendingRowId] = useState<string | null>(null);

  async function handleRowPatch(row: Vocabulary, patch: VocabularyEditInput): Promise<void> {
    // 빈 patch (변경 없음) 면 호출 skip — backend 는 200 + user_edited=true 갱신
    // 하지만 의미 없는 사이드 이펙트 회피.
    if (Object.keys(patch).length === 0) return;
    setPendingRowId(row.id);
    setError(null);
    try {
      const updated = await patchVocabulary(passageId, row.id, patch);
      onChange(vocabulary.map((v) => (v.id === row.id ? updated : v)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingRowId(null);
    }
  }

  async function handleDelete(row: Vocabulary): Promise<void> {
    if (!window.confirm(`'${row.word}' 어휘를 삭제하시겠습니까?`)) return;
    setPendingRowId(row.id);
    setError(null);
    try {
      await deleteVocabulary(passageId, row.id);
      onChange(vocabulary.filter((v) => v.id !== row.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingRowId(null);
    }
  }

  async function handleAdd(input: { word: string; meaning_ko: string }): Promise<void> {
    setError(null);
    try {
      const created = await addVocabulary(passageId, input);
      onChange([...vocabulary, created]);
      setAdding(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium text-gray-600 uppercase tracking-wide">어휘</h4>

      {vocabulary.length === 0 && !adding ? (
        <p className="text-xs text-gray-400 italic py-2">어휘가 없습니다.</p>
      ) : (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500">
              <tr>
                <th className="text-left px-3 py-2 w-[28%] font-medium">단어</th>
                <th className="text-left px-3 py-2 w-[12%] font-medium">품사</th>
                <th className="text-left px-3 py-2 w-[40%] font-medium">뜻</th>
                <th className="text-left px-3 py-2 w-[15%] font-medium">등급</th>
                <th className="w-[5%]" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {vocabulary.map((row) => (
                <VocabularyRow
                  key={row.id}
                  row={row}
                  pending={pendingRowId === row.id}
                  onPatch={(patch) => handleRowPatch(row, patch)}
                  onDelete={() => handleDelete(row)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {adding ? (
        <NewVocabularyForm onSubmit={handleAdd} onCancel={() => setAdding(false)} />
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="text-xs font-medium text-blue-600 hover:text-blue-700 transition-colors"
        >
          + 어휘 추가
        </button>
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

// ─── 단일 행 (인라인 편집) ──────────────────────────────────────────────────

function VocabularyRow({
  row,
  pending,
  onPatch,
  onDelete,
}: {
  row: Vocabulary;
  pending: boolean;
  onPatch: (patch: VocabularyEditInput) => void;
  onDelete: () => void;
}): ReactElement {
  return (
    <tr className={pending ? "bg-blue-50/30" : ""}>
      <Cell value={row.word} onCommit={(v) => onPatch({ word: v })} />
      <Cell value={row.pos ?? ""} onCommit={(v) => onPatch({ pos: v || null })} />
      <Cell value={row.meaning_ko} onCommit={(v) => onPatch({ meaning_ko: v })} />
      <Cell value={row.level_label ?? ""} onCommit={(v) => onPatch({ level_label: v || null })} />
      <td className="text-right pr-2">
        <button
          type="button"
          onClick={onDelete}
          disabled={pending}
          className="text-gray-300 hover:text-red-500 transition-colors text-base disabled:opacity-50"
          title="삭제"
        >
          ×
        </button>
      </td>
    </tr>
  );
}

// ─── 셀 (blur 시 commit) ────────────────────────────────────────────────────

function Cell({
  value,
  onCommit,
}: {
  value: string;
  onCommit: (v: string) => void;
}): ReactElement {
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  // value (외부 prop) 변경 시 draft 동기화. focus 중인 input 은 건드리지 않음 —
  // 부모 re-render 마다 draft 가 prop 으로 덮어써져 사용자 입력이 사라지는 문제
  // 회피. useEffect 로 처리 (render 중 setState 안 됨).
  useEffect(() => {
    if (document.activeElement !== inputRef.current) {
      setDraft(value);
    }
  }, [value]);

  return (
    <td className="px-3 py-1.5">
      <input
        ref={inputRef}
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          if (draft !== value) onCommit(draft);
        }}
        className="w-full bg-transparent border-0 px-0 py-0.5 text-sm text-gray-800 focus:outline-none focus:bg-blue-50/30 focus:ring-0 focus:border-0 rounded"
      />
    </td>
  );
}

// ─── 신규 행 폼 ─────────────────────────────────────────────────────────────

function NewVocabularyForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (input: { word: string; meaning_ko: string }) => void;
  onCancel: () => void;
}): ReactElement {
  const [word, setWord] = useState("");
  const [meaning, setMeaning] = useState("");
  const wordRef = useRef<HTMLInputElement>(null);

  // mount 시 1회만 단어칸 focus — ref={(el) => el?.focus()} callback ref 형태는
  // 매 render 호출되어 다른 input 에서 입력 중에도 단어칸으로 focus 빼앗는다 (NG).
  useEffect(() => {
    wordRef.current?.focus();
  }, []);

  const canSubmit = word.trim().length > 0 && meaning.trim().length > 0;

  return (
    <div className="border border-blue-200 bg-blue-50/30 rounded-lg p-3 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <input
          ref={wordRef}
          type="text"
          placeholder="단어"
          value={word}
          onChange={(e) => setWord(e.target.value)}
          className="text-sm border border-gray-200 rounded px-2 py-1 focus:outline-none focus:border-blue-400"
        />
        <input
          type="text"
          placeholder="뜻"
          value={meaning}
          onChange={(e) => setMeaning(e.target.value)}
          className="text-sm border border-gray-200 rounded px-2 py-1 focus:outline-none focus:border-blue-400"
        />
      </div>
      <div className="flex gap-2 justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1"
        >
          취소
        </button>
        <button
          type="button"
          onClick={() => {
            if (canSubmit) onSubmit({ word: word.trim(), meaning_ko: meaning.trim() });
          }}
          disabled={!canSubmit}
          className="text-xs font-medium px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed"
        >
          추가
        </button>
      </div>
    </div>
  );
}
