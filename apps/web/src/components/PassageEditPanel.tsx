/**
 * PassageEditPanel — Worksheet item 1건의 Passage 편집 panel (Stage E2-3b).
 *
 * 펼침 상태에서 GET /passages/{id} (lazy fetch) → 본문 / 해석 / 어휘 표시.
 * 내부 컴포넌트:
 *   - <PassageBodyEditor> — 영어 본문 + paragraph 편집 (Stage E3 부분)
 *   - <TranslationEditor> — 한글 해석 인라인 편집
 *   - <VocabularyTable>   — 어휘 행 인라인 편집 + 추가/삭제
 */
import { type ReactElement, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  type Passage,
  type PassageWithRelations,
  type Translation,
  type Vocabulary,
  getPassageWithRelations,
} from "../lib/api";
import { PassageBodyEditor } from "./PassageBodyEditor";
import { TranslationEditor } from "./TranslationEditor";
import { VocabularyTable } from "./VocabularyTable";

interface Props {
  passageId: string;
  /** 외부에서 펼침 상태 제어 — null 이면 panel 자체 숨김 (부모가 toggle 관리). */
  expanded: boolean;
  /** Translation/Vocabulary/Body 변경 발생 시 호출 — 부모가 미리보기 reload. */
  onContentChange?: () => void;
}

export function PassageEditPanel({
  passageId,
  expanded,
  onContentChange,
}: Props): ReactElement | null {
  const [data, setData] = useState<PassageWithRelations | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // expanded 가 처음 true 가 될 때 fetch (lazy). 이후 닫혀도 데이터 유지 — 재펼침
  // 시 stale 가능성 있지만 본 sprint 단순 정책.
  useEffect(() => {
    if (!expanded || data != null || loading) return;
    setLoading(true);
    setError(null);
    getPassageWithRelations(passageId)
      .then((result) => {
        setData(result);
      })
      .catch((e: Error) => {
        setError(e.message);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [expanded, passageId, data, loading]);

  if (!expanded) return null;

  if (loading) {
    return <div className="text-xs text-gray-400 py-3">불러오는 중…</div>;
  }
  if (error) {
    return <div className="text-xs text-red-600 py-3">Passage 조회 실패: {error}</div>;
  }
  if (data == null) return null;

  function handleTranslationSaved(updated: Translation): void {
    setData((prev) => (prev ? { ...prev, translation: updated } : prev));
    onContentChange?.();
  }

  function handleVocabularyChange(updated: Vocabulary[]): void {
    setData((prev) => (prev ? { ...prev, vocabulary: updated } : prev));
    onContentChange?.();
  }

  function handlePassageBodySaved(updated: Passage): void {
    setData((prev) => (prev ? { ...prev, passage: updated } : prev));
    onContentChange?.();
  }

  return (
    <div className="space-y-4 pt-3 pb-2 pl-4 border-l-2 border-blue-100">
      <div className="flex items-center justify-end -mb-2">
        <Link
          to={`/editor/${passageId}`}
          className="text-xs text-blue-600 hover:underline"
          title="구문분석 에디터로 이동"
        >
          구문분석 →
        </Link>
      </div>

      <PassageBodyEditor passage={data.passage} onSaved={handlePassageBodySaved} />

      <TranslationEditor
        passageId={passageId}
        translation={data.translation}
        onSaved={handleTranslationSaved}
      />

      <VocabularyTable
        passageId={passageId}
        vocabulary={data.vocabulary}
        onChange={handleVocabularyChange}
      />
    </div>
  );
}
