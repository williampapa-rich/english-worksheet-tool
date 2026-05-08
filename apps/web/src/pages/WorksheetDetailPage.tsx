import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PassageEditPanel } from "../components/PassageEditPanel";
import { type Worksheet, downloadWorksheetPdf, getWorksheet } from "../lib/api";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

/**
 * WorksheetDetailPage — /worksheets/:id 편집 페이지 골격 (Stage E2-3a).
 *
 * MVP: 읽기 + Preview + PDF 다운로드.
 *   - 메타 카드 (title / subtitle / academy / kind / template_id / orientation)
 *   - items 카운트 + passage_id 리스트 (최소 표시)
 *   - Preview iframe (GET /worksheets/{id}/preview?style=playful)
 *   - PDF 다운로드 버튼 (POST /worksheets/{id}/export.pdf)
 *
 * E2-3b 추가:
 *   - per-item 펼침 → PassageEditPanel (Translation/Vocabulary 인라인 편집).
 *
 * 후속 PR (E2-3c):
 *   - 메타 편집 + items 추가/삭제/순서 변경.
 *
 * E2-3b 합병 — 영어 본문 편집 (Stage E3 부분) 도 PassageEditPanel 에서 처리.
 */
export function WorksheetDetailPage(): ReactElement {
  const { id } = useParams<{ id: string }>();
  const [worksheet, setWorksheet] = useState<Worksheet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  /** 펼친 item id 집합 — per-item Passage 편집 panel 노출 제어. */
  const [expandedItemIds, setExpandedItemIds] = useState<Set<string>>(new Set());
  /** 미리보기 iframe cache-buster — Translation/Vocabulary/Body 변경 시 +1 → src 갱신. */
  const [previewVersion, setPreviewVersion] = useState(0);

  useEffect(() => {
    if (!id) {
      setError("id 파라미터가 없습니다.");
      return;
    }
    let cancelled = false;
    getWorksheet(id)
      .then((w) => {
        if (!cancelled) setWorksheet(w);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handlePdfDownload(): Promise<void> {
    if (!id) return;
    setDownloading(true);
    setError(null);
    try {
      await downloadWorksheetPdf(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDownloading(false);
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">학생 자료</h1>
          <Link
            to="/worksheets"
            className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            ← 목록
          </Link>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-6">
            <p className="font-medium">오류가 발생했습니다</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        {!worksheet && !error && <div className="text-gray-400 text-sm">불러오는 중…</div>}

        {worksheet && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* 메타 카드 */}
            <section className="bg-white border border-gray-100 rounded-2xl p-6">
              <h2 className="font-medium text-gray-900 text-lg mb-4">
                {worksheet.title}
                {worksheet.subtitle && (
                  <span className="text-gray-400 font-normal ml-2">· {worksheet.subtitle}</span>
                )}
              </h2>
              <dl className="space-y-2 text-sm">
                <MetaRow label="학원명" value={worksheet.branding.academy_name} />
                <MetaRow label="유형" value={kindLabel(worksheet.kind)} />
                <MetaRow label="템플릿" value={worksheet.template_id} />
                <MetaRow label="용지 방향" value={orientationLabel(worksheet.orientation)} />
                <MetaRow label="학교" value={worksheet.school} />
                <MetaRow label="학년" value={worksheet.grade} />
              </dl>

              <div className="mt-5 pt-5 border-t border-gray-100">
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  구성 ({worksheet.items.length} 개 지문)
                </h3>
                {worksheet.items.length === 0 ? (
                  <p className="text-xs text-gray-400">지문이 없습니다.</p>
                ) : (
                  <ul className="space-y-2">
                    {worksheet.items.map((item) => {
                      const isOpen = expandedItemIds.has(item.id);
                      return (
                        <li key={item.id} className="text-xs text-gray-600">
                          <div className="flex items-center gap-2 font-mono truncate">
                            <button
                              type="button"
                              onClick={() => {
                                setExpandedItemIds((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(item.id)) next.delete(item.id);
                                  else next.add(item.id);
                                  return next;
                                });
                              }}
                              className="text-gray-400 hover:text-gray-700 transition-colors w-4 text-left"
                              aria-label={isOpen ? "접기" : "펼치기"}
                            >
                              {isOpen ? "▾" : "▸"}
                            </button>
                            <span className="bg-gray-100 px-1.5 py-0.5 rounded text-gray-500">
                              {item.order}
                            </span>
                            <span className="text-gray-700 truncate" title={item.passage_id}>
                              {item.passage_id.slice(0, 8)}…
                            </span>
                            {item.include_translation && (
                              <span className="text-gray-400">·해석</span>
                            )}
                            {item.include_vocabulary && (
                              <span className="text-gray-400">·어휘</span>
                            )}
                            {item.include_syntax_annotations && (
                              <span className="text-gray-400">·구문</span>
                            )}
                          </div>
                          <PassageEditPanel
                            passageId={item.passage_id}
                            expanded={isOpen}
                            onContentChange={() => setPreviewVersion((v) => v + 1)}
                          />
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <div className="mt-5 pt-5 border-t border-gray-100 flex gap-3">
                <button
                  type="button"
                  onClick={handlePdfDownload}
                  disabled={downloading}
                  className="bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded-xl hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  {downloading ? "PDF 생성 중…" : "PDF 다운로드"}
                </button>
              </div>

              <p className="text-xs text-gray-400 mt-4">
                메타 편집 / 본문 편집은 후속 PR (E2-3c, E3) 에서 추가됩니다.
              </p>
            </section>

            {/* Preview iframe */}
            <section className="bg-white border border-gray-100 rounded-2xl overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                <h3 className="text-sm font-medium text-gray-700">미리보기</h3>
                <a
                  href={`${API_BASE_URL}/worksheets/${worksheet.id}/preview?style=playful`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-600 hover:underline"
                >
                  새 탭에서 열기 ↗
                </a>
              </div>
              <iframe
                title={`${worksheet.title} 미리보기`}
                /* previewVersion query 가 갱신되면 iframe 이 새로 fetch.
                 * 단순 reload 대신 query 로 cache 우회 (브라우저 / 서버 양쪽 안전). */
                src={`${API_BASE_URL}/worksheets/${worksheet.id}/preview?style=playful&v=${previewVersion}`}
                className="w-full h-[800px] bg-gray-50"
              />
            </section>
          </div>
        )}
      </div>
    </main>
  );
}

function MetaRow({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}): ReactElement {
  return (
    <div className="flex">
      <dt className="w-24 text-gray-400 shrink-0">{label}</dt>
      <dd className="text-gray-700">{value || <span className="text-gray-300">—</span>}</dd>
    </div>
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

function orientationLabel(o: Worksheet["orientation"]): string {
  return o === "landscape" ? "가로" : "세로";
}
