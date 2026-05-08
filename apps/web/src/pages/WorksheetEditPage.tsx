/**
 * WorksheetEditPage — 학생 자료 통합 편집 페이지 (Stage E2-3c).
 *
 * 좌우 split-pane:
 *   - 좌측: 아이템 탭 + 모드 토글 (구문분석 / 해석·어휘·본문) → 선택된 패널
 *   - 우측: 미리보기 iframe (편집 시 자동 reload)
 *
 * 구문분석 모드는 기존 EditorPoc 페이지 (`/editor/<passageId>?embed=1`) 를
 * iframe 으로 임베드. embed 플래그가 EditorPoc 의 헤더/링크를 숨겨 split-pane
 * 안에 자연 배치되도록 한다 (NRTW — 1000+줄 컴포넌트 분해 대신 iframe 격리).
 *
 * 해석·어휘·본문 모드는 PassageEditPanel 그대로 재사용.
 */
import { type ReactElement, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PassageEditPanel } from "../components/PassageEditPanel";
import { type Worksheet, getWorksheet } from "../lib/api";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

const WEB_ORIGIN = window.location.origin;

type EditMode = "syntax" | "content";

export function WorksheetEditPage(): ReactElement {
  const { id } = useParams<{ id: string }>();
  const [worksheet, setWorksheet] = useState<Worksheet | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** 현재 편집 중 item id (worksheet.items[*].id). null = 첫 item 자동 선택. */
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  /** 좌측 패널 모드 — 구문분석 (Tiptap iframe) vs 해석·어휘·본문 (인라인 편집). */
  const [mode, setMode] = useState<EditMode>("content");
  /** 미리보기 cache-buster — content 편집 시 +1. */
  const [previewVersion, setPreviewVersion] = useState(0);

  // id 변경 시 worksheet fetch + 첫 item 자동 선택. activeItemId 는 함수 안에서
  // null check 만 하므로 의존성 X — id 가 바뀌어 새 worksheet 로드 시에만 재실행.
  // biome-ignore lint/correctness/useExhaustiveDependencies: 첫 fetch 1회만 자동 선택.
  useEffect(() => {
    if (!id) {
      setError("id 파라미터가 없습니다.");
      return;
    }
    let cancelled = false;
    getWorksheet(id)
      .then((w) => {
        if (cancelled) return;
        setWorksheet(w);
        const first = w.items[0];
        if (first && activeItemId == null) {
          setActiveItemId(first.id);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) {
    return (
      <main className="h-screen flex items-center justify-center">
        <div className="text-red-700 text-sm">{error}</div>
      </main>
    );
  }
  if (!worksheet) {
    return (
      <main className="h-screen flex items-center justify-center">
        <div className="text-gray-400 text-sm">불러오는 중…</div>
      </main>
    );
  }

  const activeItem = worksheet.items.find((it) => it.id === activeItemId) ?? null;

  return (
    <main className="h-screen flex flex-col bg-gray-50">
      {/* 상단 바 */}
      <div className="h-12 bg-white border-b border-gray-200 flex items-center px-4 gap-4 shrink-0">
        <Link
          to={`/worksheets/${worksheet.id}`}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          ← 상세
        </Link>
        <div className="text-sm font-medium text-gray-900 truncate">{worksheet.title}</div>
        <div className="ml-auto flex items-center gap-2">
          <a
            href={`${API_BASE_URL}/worksheets/${worksheet.id}/preview?style=playful`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline"
          >
            새 탭 미리보기 ↗
          </a>
        </div>
      </div>

      {/* 아이템 탭 */}
      {worksheet.items.length > 1 && (
        <div className="bg-white border-b border-gray-200 px-4 flex gap-1 shrink-0 overflow-x-auto">
          {worksheet.items.map((item) => {
            const active = item.id === activeItemId;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveItemId(item.id)}
                className={`text-xs px-3 py-2 border-b-2 transition-colors whitespace-nowrap font-mono ${
                  active
                    ? "border-blue-500 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                }`}
              >
                {item.order + 1}. {item.passage_id.slice(0, 8)}…
              </button>
            );
          })}
        </div>
      )}

      {/* split-pane */}
      <div className="flex-1 flex overflow-hidden">
        {/* 좌측 — 편집 패널 */}
        <div className="w-1/2 flex flex-col border-r border-gray-200 overflow-hidden">
          {/* 모드 토글 */}
          <div className="bg-white border-b border-gray-200 px-3 py-2 flex gap-1 shrink-0">
            <ModeButton
              current={mode}
              value="content"
              onChange={setMode}
              label="해석 / 어휘 / 본문"
            />
            <ModeButton current={mode} value="syntax" onChange={setMode} label="구문분석" />
          </div>

          <div className="flex-1 overflow-auto bg-gray-50">
            {activeItem == null ? (
              <div className="p-8 text-center text-sm text-gray-400">아이템 없음.</div>
            ) : mode === "syntax" ? (
              <SyntaxEditorEmbed
                passageId={activeItem.passage_id}
                onContentChange={() => setPreviewVersion((v) => v + 1)}
              />
            ) : (
              <div className="p-4">
                <PassageEditPanel
                  key={activeItem.id}
                  passageId={activeItem.passage_id}
                  expanded={true}
                  onContentChange={() => setPreviewVersion((v) => v + 1)}
                />
              </div>
            )}
          </div>
        </div>

        {/* 우측 — 미리보기 */}
        <div className="w-1/2 flex flex-col overflow-hidden bg-white">
          <div className="bg-white border-b border-gray-200 px-3 py-2 text-xs text-gray-500 shrink-0">
            미리보기
          </div>
          <iframe
            title={`${worksheet.title} 미리보기`}
            src={`${API_BASE_URL}/worksheets/${worksheet.id}/preview?style=playful&v=${previewVersion}`}
            className="flex-1 w-full bg-gray-50"
          />
        </div>
      </div>
    </main>
  );
}

// ─── 모드 버튼 ───────────────────────────────────────────────────────────────

function ModeButton({
  current,
  value,
  onChange,
  label,
}: {
  current: EditMode;
  value: EditMode;
  onChange: (m: EditMode) => void;
  label: string;
}): ReactElement {
  const active = current === value;
  return (
    <button
      type="button"
      onClick={() => onChange(value)}
      className={`text-xs px-3 py-1.5 rounded-md transition-colors ${
        active
          ? "bg-blue-50 text-blue-700 font-medium"
          : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
      }`}
    >
      {label}
    </button>
  );
}

// ─── 구문분석 iframe 임베드 ─────────────────────────────────────────────────

/**
 * SyntaxEditorEmbed — 기존 /editor/<passageId> 페이지를 iframe 으로 임베드.
 *
 * `?embed=1` 쿼리로 EditorPoc 가 헤더/홈 링크를 숨김. 1000+줄 EditorPoc 를 직접
 * 컴포넌트화하지 않고 iframe 격리 — 충돌 위험 / PR 분량 모두 작음. 향후 컴포넌트
 * 분리 (NRTW vs 격리 트레이드오프) 가 필요해지면 별 ADR.
 *
 * 미리보기 갱신은 iframe 안 EditorPoc 가 annotation 저장 시 postMessage 송출 →
 * 본 컴포넌트 listener 가 onContentChange 호출.
 */
function SyntaxEditorEmbed({
  passageId,
  onContentChange,
}: {
  passageId: string;
  onContentChange: () => void;
}): ReactElement {
  useEffect(() => {
    function handler(event: MessageEvent): void {
      // 같은 origin 만 신뢰 — postMessage 보안.
      if (event.origin !== WEB_ORIGIN) return;
      if (
        typeof event.data === "object" &&
        event.data != null &&
        (event.data as { type?: string }).type === "ewt:annotations-saved"
      ) {
        onContentChange();
      }
    }
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [onContentChange]);

  return (
    <iframe
      title="구문분석 에디터"
      src={`/editor/${passageId}?embed=1`}
      className="w-full h-full border-0"
    />
  );
}
