import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { type Worksheet, listWorksheets } from "../lib/api";

/**
 * WorksheetListPage — GET /worksheets 목록 표시.
 *
 * Stage E2-1 (ADR-0015) 첫 페이지. 와이프가 학생 자료 워크플로우에 진입하는
 * 입구. 단건 클릭 → /worksheets/:id (편집 페이지, 후속 PR).
 *
 * MVP 정책:
 *   - kind 필터 / pagination 은 후속 PR (worksheet 수가 적은 초기에는 단순 list).
 *   - 빈 목록 시 "신규 생성" 안내 카드 (라우트는 후속 PR).
 *   - 에러는 화면에 직접 노출 (Sentry 등 외부 모니터링 도입 전).
 */
export function WorksheetListPage(): ReactElement {
  const [worksheets, setWorksheets] = useState<Worksheet[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listWorksheets({ limit: 100 })
      .then((res) => {
        if (!cancelled) setWorksheets(res.worksheets);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">학생 자료 목록</h1>
          <Link to="/" className="text-sm text-gray-500 hover:text-gray-700 transition-colors">
            ← 홈
          </Link>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-6">
            <p className="font-medium">목록을 불러오지 못했습니다</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        {worksheets === null && !error && <div className="text-gray-400 text-sm">불러오는 중…</div>}

        {worksheets !== null && worksheets.length === 0 && (
          <div className="bg-white border border-gray-100 rounded-2xl p-10 text-center">
            <p className="text-gray-600 mb-3">아직 학생 자료가 없습니다.</p>
            <p className="text-sm text-gray-400">
              생성 라우트는 후속 PR (Stage E2-2) 에서 추가됩니다.
            </p>
          </div>
        )}

        {worksheets !== null && worksheets.length > 0 && (
          <ul className="space-y-3">
            {worksheets.map((w) => (
              <li key={w.id}>
                <Link
                  to={`/worksheets/${w.id}`}
                  className="block bg-white border border-gray-100 rounded-2xl p-5 hover:border-blue-300 hover:shadow-sm transition-all"
                >
                  <div className="flex items-baseline justify-between gap-4">
                    <h2 className="font-medium text-gray-900 truncate">
                      {w.title}
                      {w.subtitle && (
                        <span className="text-gray-400 font-normal ml-2">· {w.subtitle}</span>
                      )}
                    </h2>
                    <span className="text-xs text-gray-400 shrink-0">
                      {new Date(w.updated_at).toLocaleDateString("ko-KR")}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
                    <span className="bg-gray-100 px-2 py-0.5 rounded">{kindLabel(w.kind)}</span>
                    <span className="bg-gray-100 px-2 py-0.5 rounded">{w.template_id}</span>
                    {w.branding.academy_name && (
                      <span className="text-gray-400">{w.branding.academy_name}</span>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}

function kindLabel(kind: Worksheet["kind"]): string {
  switch (kind) {
    case "student":
      return "학생용";
    case "teacher":
      return "교사용";
    case "variant":
      return "변형문제";
    default:
      return kind;
  }
}
