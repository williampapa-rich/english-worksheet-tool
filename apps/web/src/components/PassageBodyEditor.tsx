/**
 * PassageBodyEditor — 영어 본문 + paragraph 인라인 편집 (Stage E3 부분 — E2-3b 합병).
 *
 * MVP: textarea 기반. paragraphs 표현은 빈 줄 (`\n\n`) 분리 — 단순 정책.
 * Tiptap 전환 (ADR-0015 D5 a) 은 후속 PR. 현재 paragraphs 분할은 사용자가
 * 빈 줄 1개로 분리 → 저장 시 `body_text.split(/\n{2,}/)` 로 paragraphs 자동 분할.
 *
 * **주의 (사용자 알림)**:
 *   body_text 변경은 backend 가 SyntaxAnnotation 전체 삭제. 저장 전 confirm 필수.
 *
 * 동작:
 *   - paragraphs 가 있으면 `\n\n` 으로 join, 없으면 body_text 그대로 → textarea draft.
 *   - 저장: confirm → patchPassageBody({ body_text, paragraphs: split(draft) }).
 *   - 저장 후 onSaved(updated) 콜백.
 */
import { type ReactElement, useEffect, useState } from "react";
import { type Passage, patchPassageBody } from "../lib/api";

interface Props {
  passage: Passage;
  onSaved: (updated: Passage) => void;
}

function joinParagraphs(passage: Passage): string {
  if (passage.paragraphs && passage.paragraphs.length > 0) {
    return passage.paragraphs.join("\n\n");
  }
  return passage.body_text;
}

function splitParagraphs(text: string): string[] {
  // 빈 줄 (1개 이상) 으로 분리. trim 으로 양 끝 공백 제거 후 빈 항목 필터.
  return text
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
}

export function PassageBodyEditor({ passage, onSaved }: Props): ReactElement {
  const [draft, setDraft] = useState<string>(joinParagraphs(passage));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 외부 passage 갱신 시 draft 동기화.
  useEffect(() => {
    setDraft(joinParagraphs(passage));
    setError(null);
  }, [passage]);

  const original = joinParagraphs(passage);
  const dirty = draft !== original;

  async function handleSave(): Promise<void> {
    if (!dirty || saving) return;
    if (
      !window.confirm(
        "본문을 수정하면 기존 구문분석 (annotation) 이 *모두 삭제* 됩니다. 진행하시겠습니까?"
      )
    ) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const paragraphs = splitParagraphs(draft);
      const body_text = paragraphs.join("\n\n");
      const updated = await patchPassageBody(passage.id, { body_text, paragraphs });
      onSaved(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium text-gray-600 uppercase tracking-wide">영어 본문</h4>
        <div className="flex items-center gap-2">
          {dirty && (
            <span className="text-[10px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
              저장 안 됨
            </span>
          )}
        </div>
      </div>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        className="w-full min-h-[140px] text-sm text-gray-800 leading-relaxed border border-gray-200 rounded-lg p-3 focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400 resize-y font-mono"
        placeholder="영어 본문 (paragraph 는 빈 줄로 분리)"
      />
      <p className="text-[10px] text-gray-400">
        빈 줄 1개로 paragraph 를 분리. 저장 시 기존 구문분석은 삭제됩니다.
      </p>
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleSave}
          disabled={!dirty || saving}
          className="text-xs font-medium px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed"
        >
          {saving ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
