/**
 * TranslationEditor — Translation 인라인 편집 컴포넌트 (Stage E2-3b).
 *
 * MVP: textarea 기반. ADR-0015 D5 의 (a) Tiptap 재사용 결정은 `<PassageBodyEditor>`
 * 의 본문 편집 (E3) 에서 우선 적용. Translation 은 일반 한국어 단락 텍스트라
 * 형식 마크 없는 textarea 가 단순. Tiptap 전환은 후속 PR.
 *
 * 동작:
 *   - props.translation == null → "해석이 없습니다 — LLM 보강 필요" 안내.
 *   - props.translation != null → text 를 textarea 로 편집. dirty state 표시.
 *     저장 버튼 = patchTranslation 호출. 저장 후 props.onSaved(updated) 콜백.
 *   - created_by="user" 일 때만 사용자 편집 흔적 (badge) 표시.
 */
import { type ReactElement, useEffect, useState } from "react";
import { type Translation, patchTranslation } from "../lib/api";

interface Props {
  passageId: string;
  translation: Translation | null;
  onSaved: (updated: Translation) => void;
}

export function TranslationEditor({ passageId, translation, onSaved }: Props): ReactElement {
  const [draft, setDraft] = useState<string>(translation?.text ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // props.translation 변경 시 (다른 passage 로 전환, 외부 갱신) draft 동기화.
  useEffect(() => {
    setDraft(translation?.text ?? "");
    setError(null);
  }, [translation]);

  if (translation == null) {
    return (
      <div className="text-xs text-gray-400 italic py-2">
        해석이 없습니다. POST /passages/{passageId}/translation 으로 먼저 생성하세요.
      </div>
    );
  }

  const dirty = draft !== translation.text;

  async function handleSave(): Promise<void> {
    if (!dirty || saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await patchTranslation(passageId, draft);
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
        <h4 className="text-xs font-medium text-gray-600 uppercase tracking-wide">한글 해석</h4>
        <div className="flex items-center gap-2">
          {translation.created_by === "user" && (
            <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
              사용자 편집
            </span>
          )}
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
        className="w-full min-h-[100px] text-sm text-gray-800 leading-relaxed border border-gray-200 rounded-lg p-3 focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400 resize-y"
        placeholder="한글 해석"
      />
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
