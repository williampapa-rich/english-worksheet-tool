/**
 * WorksheetMetaForm — Worksheet 메타 편집 모달 (Stage E2-3d).
 *
 * ADR-0015 Stage E2-3 잔존 항목. 통합 편집 페이지에서 메타 편집 진입점.
 * title / subtitle / kind / template_id / orientation / instruction /
 * branding (academy_name / primary_color / logo_url) / school / grade /
 * exam_date / time_limit 12개 필드.
 *
 * UX 결정:
 *   - 모달 (WorksheetItemList AddItemModal 과 동일 패턴) — 한 화면에 12개
 *     필드를 차분히. 인라인 편집은 화면 좁음.
 *   - 폼 dirty 시에만 저장 버튼 활성화 — patch 가 빈 dict 면 백엔드 422.
 *   - title 만 required (백엔드 NOT NULL 강제) — 나머지는 빈값 = ``null`` 또는
 *     "변경 없음" 으로 처리.
 *   - branding.secondary_color 는 현재 템플릿 미사용 (ADR-0010 §D6) — 폼 미노출.
 *
 * 백엔드 라우트: PATCH /worksheets/{id} (PR #49 머지). 본 PR 은 프론트만.
 */
import { type ReactElement, useState } from "react";
import { type Worksheet, type WorksheetMetaPatchInput, patchWorksheet } from "../lib/api";

const WORKSHEET_KINDS: ReadonlyArray<{ value: "student" | "teacher" | "variant"; label: string }> =
  [
    { value: "student", label: "학생용" },
    { value: "teacher", label: "교사용" },
    { value: "variant", label: "변형문제집" },
  ];

const ORIENTATIONS: ReadonlyArray<{ value: "portrait" | "landscape"; label: string }> = [
  { value: "portrait", label: "세로 (Portrait)" },
  { value: "landscape", label: "가로 (Landscape)" },
];

/** 현재 활성 템플릿 id 목록. playful / classic / modern 3종 (Phase 2 baseline). */
const TEMPLATE_IDS: ReadonlyArray<string> = ["playful", "classic", "modern"];

export function WorksheetMetaForm({
  worksheet,
  onClose,
  onSaved,
}: {
  worksheet: Worksheet;
  onClose: () => void;
  /** 저장 성공 시 부모 통지 — 보통 worksheet refetch + 미리보기 reload. */
  onSaved: (updated: Worksheet) => void;
}): ReactElement {
  // 초기값 = 현재 worksheet. trim 없이 raw 값 보존 (사용자 입력 의도 존중).
  const [title, setTitle] = useState<string>(worksheet.title);
  const [subtitle, setSubtitle] = useState<string>(worksheet.subtitle ?? "");
  const [kind, setKind] = useState<"student" | "teacher" | "variant">(worksheet.kind);
  const [templateId, setTemplateId] = useState<string>(worksheet.template_id);
  const [orientation, setOrientation] = useState<"portrait" | "landscape">(worksheet.orientation);
  const [instruction, setInstruction] = useState<string>(worksheet.instruction ?? "");

  // branding sub-fields (3종 — secondary_color 는 현재 템플릿 미사용).
  const [academyName, setAcademyName] = useState<string>(worksheet.branding.academy_name ?? "");
  const [primaryColor, setPrimaryColor] = useState<string>(worksheet.branding.primary_color ?? "");
  const [logoUrl, setLogoUrl] = useState<string>(worksheet.branding.logo_url ?? "");

  // 학생 정보 메타 (4종).
  const [school, setSchool] = useState<string>(worksheet.school ?? "");
  const [grade, setGrade] = useState<string>(worksheet.grade ?? "");
  const [examDate, setExamDate] = useState<string>(worksheet.exam_date ?? "");
  const [timeLimit, setTimeLimit] = useState<string>(worksheet.time_limit ?? "");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * buildPatch — 현재 폼 값과 worksheet 값을 비교해 변경된 필드만 patch dict 에 담는다.
   *
   * 빈 string → ``null`` 로 변환 (nullable 필드만 — title / kind / template_id /
   * orientation 은 NOT NULL 이므로 빈 string 은 422 유발. 호출자가 사전에 차단).
   * branding 은 *통째 교체* (백엔드 정책) — 어떤 sub-field 라도 변경되면 전체 dict.
   */
  function buildPatch(): WorksheetMetaPatchInput {
    const patch: WorksheetMetaPatchInput = {};

    if (title !== worksheet.title) patch.title = title;
    if ((subtitle || null) !== worksheet.subtitle) patch.subtitle = subtitle || null;
    if (kind !== worksheet.kind) patch.kind = kind;
    if (templateId !== worksheet.template_id) patch.template_id = templateId;
    if (orientation !== worksheet.orientation) patch.orientation = orientation;
    if ((instruction || null) !== worksheet.instruction) patch.instruction = instruction || null;

    const brandingChanged =
      (academyName || null) !== worksheet.branding.academy_name ||
      (primaryColor || null) !== worksheet.branding.primary_color ||
      (logoUrl || null) !== worksheet.branding.logo_url;
    if (brandingChanged) {
      patch.branding = {
        academy_name: academyName || null,
        primary_color: primaryColor || null,
        secondary_color: worksheet.branding.secondary_color ?? null,
        logo_url: logoUrl || null,
      };
    }

    if ((school || null) !== worksheet.school) patch.school = school || null;
    if ((grade || null) !== worksheet.grade) patch.grade = grade || null;
    if ((examDate || null) !== worksheet.exam_date) patch.exam_date = examDate || null;
    if ((timeLimit || null) !== worksheet.time_limit) patch.time_limit = timeLimit || null;

    return patch;
  }

  const patch = buildPatch();
  const dirty = Object.keys(patch).length > 0;
  const titleEmpty = !title.trim();

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    if (titleEmpty) {
      setError("제목은 필수입니다.");
      return;
    }
    if (!dirty) {
      // 변경 없음 — 모달 그냥 닫기 (백엔드 422 회피).
      onClose();
      return;
    }
    setSubmitting(true);
    try {
      const updated = await patchWorksheet(worksheet.id, patch);
      onSaved(updated);
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
        className="bg-white rounded-xl p-6 w-full max-w-3xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
        // biome-ignore lint/a11y/useSemanticElements: <dialog> 가 정중앙 정렬을 강제로 깨서 div 사용 (다른 모달과 동일 패턴)
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-900">메타 편집</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-xl leading-none"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* 기본 정보 ─────────────────────────────────────── */}
          <fieldset className="space-y-3">
            <legend className="text-sm font-semibold text-gray-700">기본</legend>

            <FieldRow label="제목" required>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={submitting}
                maxLength={255}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </FieldRow>

            <FieldRow label="부제목 (선택)">
              <input
                type="text"
                value={subtitle}
                onChange={(e) => setSubtitle(e.target.value)}
                disabled={submitting}
                maxLength={255}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </FieldRow>

            <FieldRow label="유형">
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as typeof kind)}
                disabled={submitting}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {WORKSHEET_KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </select>
            </FieldRow>

            <FieldRow label="템플릿">
              <select
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
                disabled={submitting}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {TEMPLATE_IDS.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </FieldRow>

            <FieldRow label="용지 방향">
              <select
                value={orientation}
                onChange={(e) => setOrientation(e.target.value as typeof orientation)}
                disabled={submitting}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {ORIENTATIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </FieldRow>

            <FieldRow label="안내문 (선택)">
              <textarea
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                disabled={submitting}
                maxLength={2000}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="예: 다음 글을 읽고 한글 해석과 어휘를 학습하세요."
              />
            </FieldRow>
          </fieldset>

          {/* 브랜딩 ───────────────────────────────────────── */}
          <fieldset className="space-y-3 pt-3 border-t border-gray-200">
            <legend className="text-sm font-semibold text-gray-700">브랜딩</legend>

            <FieldRow label="학원 이름">
              <input
                type="text"
                value={academyName}
                onChange={(e) => setAcademyName(e.target.value)}
                disabled={submitting}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="예: 윌리엄 영어학원"
              />
            </FieldRow>

            <FieldRow label="대표 색상">
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={primaryColor || "#1F4E79"}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  disabled={submitting}
                  className="w-12 h-9 border border-gray-300 rounded-md cursor-pointer disabled:cursor-not-allowed"
                />
                <input
                  type="text"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  disabled={submitting}
                  placeholder="#1F4E79"
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                {primaryColor && (
                  <button
                    type="button"
                    onClick={() => setPrimaryColor("")}
                    disabled={submitting}
                    className="text-xs text-gray-500 hover:text-gray-700 px-2"
                  >
                    초기화
                  </button>
                )}
              </div>
            </FieldRow>

            <FieldRow label="로고 URL">
              <input
                type="text"
                value={logoUrl}
                onChange={(e) => setLogoUrl(e.target.value)}
                disabled={submitting}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="https://example.com/logo.png"
              />
            </FieldRow>
          </fieldset>

          {/* 학생 정보 ─────────────────────────────────── */}
          <fieldset className="space-y-3 pt-3 border-t border-gray-200">
            <legend className="text-sm font-semibold text-gray-700">학생 정보</legend>

            <div className="grid grid-cols-2 gap-3">
              <FieldRow label="학교">
                <input
                  type="text"
                  value={school}
                  onChange={(e) => setSchool(e.target.value)}
                  disabled={submitting}
                  maxLength={255}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </FieldRow>

              <FieldRow label="학년/반">
                <input
                  type="text"
                  value={grade}
                  onChange={(e) => setGrade(e.target.value)}
                  disabled={submitting}
                  maxLength={64}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </FieldRow>

              <FieldRow label="시험 일시">
                <input
                  type="text"
                  value={examDate}
                  onChange={(e) => setExamDate(e.target.value)}
                  disabled={submitting}
                  maxLength={64}
                  placeholder="예: 2026-05-15"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </FieldRow>

              <FieldRow label="제한 시간">
                <input
                  type="text"
                  value={timeLimit}
                  onChange={(e) => setTimeLimit(e.target.value)}
                  disabled={submitting}
                  maxLength={32}
                  placeholder="예: 50분"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </FieldRow>
            </div>
          </fieldset>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-3 text-sm">
              {error}
            </div>
          )}

          <div className="flex items-center justify-between gap-2 pt-2 border-t border-gray-200">
            <div className="text-xs text-gray-500">
              {dirty ? `변경된 필드 ${Object.keys(patch).length}개` : "변경 없음"}
            </div>
            <div className="flex gap-2">
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
                disabled={submitting || titleEmpty}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? "저장 중…" : dirty ? "저장" : "닫기"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── 공통 필드 행 ────────────────────────────────────────────────────────────

function FieldRow({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}): ReactElement {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: input 은 children 으로 항상 nested 됨 (호출부 강제). lint 가 ReactNode children 까지 못 추적.
    <label className="block">
      <span className="block text-xs font-medium text-gray-600 mb-1">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </span>
      {children}
    </label>
  );
}
