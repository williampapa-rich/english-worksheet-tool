import type { ReactElement } from "react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createWorksheet, extractPassageText } from "../lib/api";

/**
 * WorksheetNewPage — 신규 학생 자료 생성 (Stage E2-2).
 *
 * 한 페이지에서 §1.1 의 1+5 단계 처리:
 *   1. 영어 지문 텍스트 입력 → POST /passages/extract (kind=text) → passage_id 확보.
 *   2. 메타 입력 (제목/subtitle/branding) → POST /worksheets/ → worksheet_id.
 *   3. 생성 후 /worksheets/:id (E2-3 편집 페이지) 로 이동.
 *
 * MVP 단순화:
 *   - kind=student / template_id=playful 고정 (와이프 1차 사용자 흐름).
 *   - LLM 보강 (translation / vocabulary) 은 편집 페이지에서 별도 트리거.
 *   - image / pdf 업로드는 후속 PR.
 *   - branding 은 academy_name 1개만 (color preset 은 user_preferences 도입 시 이중화).
 *
 * 에러 정책: 단계별 에러를 화면 상단에 표시 + 입력 보존 (재시도).
 */
export function WorksheetNewPage(): ReactElement {
  const navigate = useNavigate();
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [academyName, setAcademyName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    if (!body.trim() || !title.trim()) {
      setError("지문과 제목을 모두 입력해주세요.");
      return;
    }
    setSubmitting(true);
    try {
      const passage = await extractPassageText(body);
      const worksheet = await createWorksheet({
        title: title.trim(),
        subtitle: subtitle.trim() || null,
        kind: "student",
        template_id: "playful",
        branding: { academy_name: academyName.trim() || null },
        items: [
          {
            passage_id: passage.id,
            order: 0,
            include_translation: true,
            include_vocabulary: true,
            include_syntax_annotations: false,
          },
        ],
      });
      navigate(`/worksheets/${worksheet.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">신규 학생 자료</h1>
          <Link
            to="/worksheets"
            className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            ← 목록
          </Link>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-6">
            <p className="font-medium">생성하지 못했습니다</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="ws-title" className="block text-sm font-medium text-gray-700 mb-1.5">
              제목
            </label>
            <input
              id="ws-title"
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="예: 고2 영어 — Zero-Waste Stores"
              className="w-full bg-white border border-gray-200 rounded-xl px-4 py-2.5 focus:outline-none focus:border-blue-400"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="ws-subtitle"
                className="block text-sm font-medium text-gray-700 mb-1.5"
              >
                부제 <span className="text-gray-400 font-normal">(선택)</span>
              </label>
              <input
                id="ws-subtitle"
                type="text"
                value={subtitle}
                onChange={(e) => setSubtitle(e.target.value)}
                placeholder="예: Week 01"
                className="w-full bg-white border border-gray-200 rounded-xl px-4 py-2.5 focus:outline-none focus:border-blue-400"
              />
            </div>
            <div>
              <label
                htmlFor="ws-academy"
                className="block text-sm font-medium text-gray-700 mb-1.5"
              >
                학원명 <span className="text-gray-400 font-normal">(선택)</span>
              </label>
              <input
                id="ws-academy"
                type="text"
                value={academyName}
                onChange={(e) => setAcademyName(e.target.value)}
                placeholder="예: 테스트 학원"
                className="w-full bg-white border border-gray-200 rounded-xl px-4 py-2.5 focus:outline-none focus:border-blue-400"
              />
            </div>
          </div>

          <div>
            <label htmlFor="ws-body" className="block text-sm font-medium text-gray-700 mb-1.5">
              영어 지문
            </label>
            <textarea
              id="ws-body"
              required
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={10}
              placeholder="여기에 영어 지문을 붙여넣으세요. 추출 후 한글 해석 / 어휘 박스를 LLM 으로 보강할 수 있습니다."
              className="w-full bg-white border border-gray-200 rounded-xl px-4 py-3 font-mono text-sm focus:outline-none focus:border-blue-400 resize-y"
            />
            <p className="text-xs text-gray-400 mt-1">
              생성 후 편집 페이지에서 한글 해석 / 어휘 / 구문분석을 추가합니다.
            </p>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={submitting}
              className="bg-blue-600 text-white font-medium px-6 py-2.5 rounded-xl hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {submitting ? "생성 중…" : "생성하기"}
            </button>
            <Link
              to="/worksheets"
              className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
            >
              취소
            </Link>
          </div>
        </form>
      </div>
    </main>
  );
}
