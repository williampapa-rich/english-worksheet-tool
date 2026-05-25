/**
 * api.ts — backend REST API 클라이언트 (P1-6, P1-annotation-input-dto, C-2b)
 *
 * fetch 직접 사용. axios 등 라이브러리 없음.
 * VITE_API_BASE_URL 환경변수 없으면 http://localhost:8000 으로 fallback.
 *
 * P1-annotation-input-dto 변경:
 *   replaceAnnotations 에서 stub (TENANT_ID / WORKSPACE_ID 상수, annotation_id drop) 제거.
 *   backend 가 SyntaxAnnotationInput DTO 를 받아 서버-side 컨텍스트를 직접 주입하므로,
 *   클라이언트는 SerializedAnnotation 을 그대로 보내면 된다.
 *   annotation_id 는 에디터 chip ID 로 backend 가 영속화한다 (옵션 A).
 *
 * C-2b 추가:
 *   - getPreference(key, workspaceId?) — GET /preferences/{key}?workspace_id=...
 *   - setPreference(key, value, options?) — PATCH /preferences/{key}
 *   UserPreference / UserPreferencePatchInput TypeScript 타입 정의
 *
 * 함수:
 *   - getPassage(id) — GET /passages/{id}
 *   - getAnnotations(passageId) — GET /passages/{id}/annotations → annotations[]
 *   - replaceAnnotations(passageId, annotations) — POST /passages/{id}/annotations
 *   - downloadPassageHwpx(passageId) — GET /passages/{id}/hwpx → 브라우저 다운로드 트리거
 *   - getPreference(key, workspaceId?) — GET /preferences/{key}
 *   - setPreference(key, value, options?) — PATCH /preferences/{key}
 */

import type { SerializedAnnotation } from "@english-worksheet-tool/editor";

// ---------------------------------------------------------------------------
// 설정
// ---------------------------------------------------------------------------

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// 도메인 타입 — backend SyntaxAnnotation / Passage / UserPreference 최소 인터페이스
// (full schema 는 shared/schemas/*.py 가 source of truth)
// ---------------------------------------------------------------------------

// ─── UserPreference (C-2b) ────────────────────────────────────────────────

/**
 * UserPreference<T> — GET /preferences/{key} 응답 형태.
 *
 * shared/schemas/user_preference.py UserPreference 의 TypeScript 미러.
 * T 는 value JSONB 의 typed form — 예: SentenceRolePresetValue.
 *
 * 필드 정책:
 *   - id / tenant_id / user_id / created_at / updated_at: 서버 관리 메타데이터
 *   - key: dot-notation (예: "preset.sentence_role")
 *   - value: T (key 별 Pydantic 모델로 backend 에서 검증)
 *   - version: 낙관적 동시성 버전 — 다음 PATCH body 에 echo 해야 함
 *   - workspace_id: Optional (워크스페이스 범위 분리)
 */
export interface UserPreference<T = Record<string, unknown>> {
  id: string;
  tenant_id: string;
  user_id: string;
  workspace_id: string | null;
  key: string;
  value: T;
  version: number;
  created_at: string;
  updated_at: string;
}

/**
 * UserPreferencePatchInput — PATCH /preferences/{key} 요청 body.
 *
 * shared/schemas/user_preference.py UserPreferencePatchInput 의 TypeScript 미러.
 * tenant_id / user_id / key 는 서버-side 주입 — 클라이언트가 보내지 않음.
 */
export interface UserPreferencePatchInput<T = Record<string, unknown>> {
  value: T;
  workspace_id?: string | null;
  version?: number | null;
}

/**
 * SentenceRolePresetValue — "preset.sentence_role" key 의 value schema.
 *
 * shared/schemas/user_preference.py SentenceRolePresetValue 의 TypeScript 미러.
 * presets: 성분 라벨 preset 리스트 (예: ["S", "V", "O", "OC", "SC"]).
 */
export interface SentenceRolePresetValue {
  presets: string[];
}

/**
 * PreferenceConflictError — PATCH 409 충돌 (낙관적 동시성 버전 불일치).
 *
 * ADR-0009 §D8: 다른 탭/디바이스에서 선행 PATCH 가 완료된 경우.
 * caller 는 최신 GET 후 재시도해야 한다.
 */
export class PreferenceConflictError extends Error {
  constructor(
    message: string,
    public readonly detail: unknown
  ) {
    super(message);
    this.name = "PreferenceConflictError";
  }
}

/** Passage — GET /passages/{id} 응답의 최소 필드 */
export interface Passage {
  id: string;
  body_text: string;
  paragraphs?: string[] | null;
  title?: string | null;
  source_material?: string | null;
}

/**
 * VariantKind — POST /questions/{id}/variants/{kind} 의 kind 경로 파라미터.
 *
 * shared/schemas/question.py VariantKind enum 의 TypeScript 미러 (snake_case).
 * catalog v0.4 §3.2.0 V1~V10 정합.
 */
export type VariantKind =
  | "original"
  | "cross_type"
  | "vocabulary_swap"
  | "vocabulary_inline"
  | "grammar_swap"
  | "grammar_inline"
  | "blank_inference"
  | "topic_main_idea_swap"
  | "order_shuffle"
  | "sentence_insertion_shift"
  | "irrelevant_sentence_inject"
  | "summary_blank_swap";

export interface CompatibleTypeInfo {
  type: string;
  label: string;
  level: string;
}

/**
 * Question — POST /passages/extract 응답 / POST /questions/{id}/variants/{kind} 응답.
 *
 * shared/schemas/question.py Question 의 TypeScript 미러 (최소 필드).
 * UI 에서 사용하는 필드만 선언.
 */
export interface Question {
  id: string;
  passage_id: string;
  type: string;
  variant_kind: VariantKind;
  derived_from_question_id: string | null;
  number: number | null;
  question_text: string;
  choices: string[];
  variant_metadata: Record<string, unknown> | null;
  answer: number;
  explanation: string;
  uniqueness_validated: boolean;
  uniqueness_validator_note: string | null;
}

/**
 * ExtractedPassageResult — POST /passages/extract 응답의 results[] 1건.
 *
 * shared/schemas/passage.py PassageWithRelations 의 TypeScript 미러 (최소 필드).
 * questions 포함 (Phase 3 — 변형 생성 진입점).
 */
export interface ExtractedPassageResult {
  passage: Passage;
  questions: Question[];
  translation: Translation | null;
  vocabulary: Vocabulary[];
}

/** Translation — Passage 1건의 한국어 해석 (1:1).
 *
 * shared/schemas/translation.py Translation 의 TypeScript 미러 (최소 필드).
 */
export interface Translation {
  id: string;
  tenant_id: string;
  workspace_id: string;
  passage_id: string;
  language: "ko";
  text: string;
  /** "llm" | "user" — 사용자 편집 시 자동으로 "user" 갱신. */
  created_by: "llm" | "user";
}

/** Vocabulary — Passage 종속 어휘 항목.
 *
 * shared/schemas/vocabulary.py Vocabulary 의 TypeScript 미러 (최소 필드).
 */
export interface Vocabulary {
  id: string;
  tenant_id: string;
  workspace_id: string;
  passage_id: string;
  word: string;
  headword_normalized: string;
  pos?: string | null;
  meaning_ko: string;
  level_label?: string | null;
  /** "llm" | "user" | "frequency_filter". user_edited 와 함께 ADR-0013 보존 정책 입력. */
  selected_by: "llm" | "user" | "frequency_filter";
  user_edited: boolean;
}

/** PassageWithRelations — GET /passages/{id} 전체 응답.
 *
 * B1 (PR #51) 이후 translation / vocabulary 도 함께 반환된다.
 */
export interface PassageWithRelations {
  passage: Passage;
  translation: Translation | null;
  vocabulary: Vocabulary[];
  // questions 는 본 sprint 범위 외 — 필요 시 별도 호출.
}

/** SyntaxAnnotation — GET /passages/{id}/annotations 응답의 annotation item */
export interface SyntaxAnnotation extends SerializedAnnotation {
  id?: string | null;
  passage_id?: string | null;
}

// ---------------------------------------------------------------------------
// 내부 헬퍼
// ---------------------------------------------------------------------------

/**
 * checkOk — response.ok 체크 후 에러 throw.
 * response body 의 detail 메시지 포함 (FastAPI validation error 호환).
 */
async function checkOk(response: Response): Promise<void> {
  if (!response.ok) {
    let detail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // JSON 파싱 실패 시 기본 메시지 유지
    }
    throw new Error(detail);
  }
}

// ---------------------------------------------------------------------------
// 공개 API
// ---------------------------------------------------------------------------

/**
 * getPassage — GET /passages/{id}
 *
 * backend 응답 형태: { passage: Passage, questions: [...], translation, vocabulary }
 * passage 필드만 추출해 반환한다 (호환성 유지).
 *
 * translation / vocabulary 도 같이 필요하면 ``getPassageWithRelations`` 사용.
 */
export async function getPassage(id: string): Promise<Passage> {
  const response = await fetch(`${API_BASE_URL}/passages/${id}`);
  await checkOk(response);
  const body = (await response.json()) as { passage: Passage };
  return body.passage;
}

/**
 * getPassageWithRelations — GET /passages/{id}
 *
 * passage + translation + vocabulary 전체 반환. E2-3b TranslationEditor /
 * VocabularyTable 진입 시 사용.
 */
export async function getPassageWithRelations(id: string): Promise<PassageWithRelations> {
  const response = await fetch(`${API_BASE_URL}/passages/${id}`);
  await checkOk(response);
  const body = (await response.json()) as PassageWithRelations;
  return {
    passage: body.passage,
    translation: body.translation ?? null,
    vocabulary: body.vocabulary ?? [],
  };
}

/**
 * patchPassageBody — PATCH /passages/{id}
 *
 * 본문 + paragraph 분할 편집 (ADR-0015 Stage E1-e).
 *
 * **주의**: backend 가 동일 트랜잭션에서 ``SyntaxAnnotation`` 전체 삭제 — body_text
 * 의 character offset 이 깨지므로. caller 는 호출 전 사용자에게 confirm 필수.
 *
 * paragraphs 빈 배열 = body_text 단일 paragraph 의도.
 */
export async function patchPassageBody(
  passageId: string,
  body: { body_text: string; paragraphs?: string[] }
): Promise<Passage> {
  const response = await fetch(`${API_BASE_URL}/passages/${passageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      body_text: body.body_text,
      paragraphs: body.paragraphs ?? [],
    }),
  });
  await checkOk(response);
  return (await response.json()) as Passage;
}

/**
 * patchTranslation — PATCH /passages/{id}/translation
 *
 * 사용자 인라인 편집. backend 가 ``created_by="user"`` 자동 갱신.
 * Translation 이 존재하지 않으면 404 — 먼저 LLM 보강 (POST /translation) 필요.
 */
export async function patchTranslation(passageId: string, text: string): Promise<Translation> {
  const response = await fetch(`${API_BASE_URL}/passages/${passageId}/translation`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  await checkOk(response);
  return (await response.json()) as Translation;
}

/**
 * VocabularyEditInput — patchVocabulary body. 모든 필드 optional, None=변경 없음.
 */
export interface VocabularyEditInput {
  word?: string;
  pos?: string | null;
  meaning_ko?: string;
  level_label?: string | null;
  headword_normalized?: string;
}

/**
 * patchVocabulary — PATCH /passages/{passageId}/vocabulary/{vocabularyId}
 *
 * 행 단위 편집. backend 가 ``user_edited=true`` 자동 갱신.
 */
export async function patchVocabulary(
  passageId: string,
  vocabularyId: string,
  patch: VocabularyEditInput
): Promise<Vocabulary> {
  const response = await fetch(`${API_BASE_URL}/passages/${passageId}/vocabulary/${vocabularyId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  await checkOk(response);
  return (await response.json()) as Vocabulary;
}

/**
 * VocabularyManualCreateInput — addVocabulary body. word / meaning_ko 필수.
 */
export interface VocabularyManualCreateInput {
  word: string;
  meaning_ko: string;
  pos?: string | null;
  level_label?: string | null;
  headword_normalized?: string;
}

/**
 * addVocabulary — POST /passages/{id}/vocabulary/manual
 *
 * 사용자 직접 어휘 행 추가. ``selected_by="user"`` 로 영속화.
 */
export async function addVocabulary(
  passageId: string,
  input: VocabularyManualCreateInput
): Promise<Vocabulary> {
  const response = await fetch(`${API_BASE_URL}/passages/${passageId}/vocabulary/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  await checkOk(response);
  return (await response.json()) as Vocabulary;
}

/**
 * deleteVocabulary — DELETE /passages/{passageId}/vocabulary/{vocabularyId}
 *
 * 모든 항목 (LLM/USER) 삭제 허용 (ADR-0015 D3 결정 b).
 */
export async function deleteVocabulary(passageId: string, vocabularyId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/passages/${passageId}/vocabulary/${vocabularyId}`, {
    method: "DELETE",
  });
  await checkOk(response);
}

/**
 * getAnnotations — GET /passages/{id}/annotations
 *
 * 응답 `{ annotations: [...] }` 에서 배열을 추출해 반환한다.
 */
export async function getAnnotations(passageId: string): Promise<SyntaxAnnotation[]> {
  const response = await fetch(`${API_BASE_URL}/passages/${passageId}/annotations`);
  await checkOk(response);
  const body = (await response.json()) as { annotations: SyntaxAnnotation[] };
  return body.annotations ?? [];
}

/**
 * replaceAnnotations — POST /passages/{id}/annotations
 *
 * replace-all 방식으로 기존 annotation 을 교체한다.
 *
 * P1-annotation-input-dto: backend 가 SyntaxAnnotationInput DTO 를 수신하므로
 * 클라이언트는 SerializedAnnotation 을 그대로 전달하면 된다.
 *   - tenant_id / workspace_id / passage_id: backend 가 TenantContext + path param 으로 주입.
 *   - annotation_id: 에디터 chip ID 로 backend 가 영속화 (옵션 A).
 *
 * 반환: 저장된 SyntaxAnnotation[] (DB 에서 id / passage_id 채워진 것).
 */
export async function replaceAnnotations(
  passageId: string,
  annotations: SerializedAnnotation[]
): Promise<SyntaxAnnotation[]> {
  const response = await fetch(`${API_BASE_URL}/passages/${passageId}/annotations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ annotations }),
  });
  await checkOk(response);
  const body = (await response.json()) as { annotations: SyntaxAnnotation[] };
  return body.annotations ?? [];
}

/**
 * getPreference — GET /preferences/{key}
 *
 * 해당 key 의 환경설정 1건을 반환한다.
 *   - 200 → UserPreference<T> 반환
 *   - 404 → null 반환 (최초 진입 시 DB 행 없음)
 *   - 422 (unknown key) → Error throw (backend 에 등록되지 않은 key)
 *   - 기타 에러 → Error throw
 *
 * workspace_id 옵션: 워크스페이스 범위 분리가 필요한 key 에만 전달.
 * 테넌트 전역 설정이면 생략.
 *
 * 낙관적 동시성: 반환된 UserPreference.version 을 다음 setPreference 호출 시 echo.
 */
export async function getPreference<T = Record<string, unknown>>(
  key: string,
  workspaceId?: string
): Promise<UserPreference<T> | null> {
  const url = new URL(`${API_BASE_URL}/preferences/${encodeURIComponent(key)}`);
  if (workspaceId) url.searchParams.set("workspace_id", workspaceId);

  const response = await fetch(url.toString());

  if (response.status === 404) return null;

  await checkOk(response);
  const body = (await response.json()) as UserPreference<T>;
  return body;
}

/**
 * setPreference — PATCH /preferences/{key}
 *
 * key 에 해당하는 환경설정을 upsert 한다.
 *   - 200 → 저장된 UserPreference<T> 반환 (version +1 포함)
 *   - 409 (version conflict) → PreferenceConflictError throw
 *   - 422 (validation error / unknown key) → Error throw
 *   - 기타 에러 → Error throw
 *
 * 낙관적 동시성 흐름:
 *   1. getPreference → preference.version 확인
 *   2. setPreference(..., { version: preference.version }) 로 echo
 *   3. 다른 탭/디바이스에서 선행 PATCH 시 409 → PreferenceConflictError
 *   4. 최신 getPreference 후 재시도 필요
 *
 * 최초 생성 (DB 행 없음) 시 version 을 omit 하거나 null 로 전달 — 검사 안 함.
 */
export async function setPreference<T = Record<string, unknown>>(
  key: string,
  value: T,
  options?: { workspaceId?: string; version?: number }
): Promise<UserPreference<T>> {
  const body: UserPreferencePatchInput<T> = {
    value,
    ...(options?.workspaceId != null ? { workspace_id: options.workspaceId } : {}),
    ...(options?.version != null ? { version: options.version } : {}),
  };

  const response = await fetch(`${API_BASE_URL}/preferences/${encodeURIComponent(key)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (response.status === 409) {
    let detail: unknown = undefined;
    try {
      detail = (await response.json()) as unknown;
    } catch {
      // JSON 파싱 실패 무시
    }
    throw new PreferenceConflictError(
      `preferences/${key} version conflict (409). 최신 GET 후 재시도.`,
      detail
    );
  }

  await checkOk(response);
  const saved = (await response.json()) as UserPreference<T>;
  return saved;
}

/**
 * downloadPassageHwpx — GET /passages/{id}/hwpx 후 브라우저 다운로드 트리거.
 *
 * @deprecated ADR-0008 (2026-05-04) 결정으로 HWPX 출력 경로가 PDF 로 전환됨.
 *   - P1-9 와이프 검수 D 등급 ("냉정하게 사용 불가") — HWPX 렌더러 한컴 layout 함정 누적.
 *   - ADR-0008 §5 채택안 A: HTML→PDF (window.print + CSS @page A4 portrait).
 *   - 신규 코드에서 이 함수를 호출하지 말 것. EditorPoc 의 HWPX 버튼은 숨김 처리됨.
 *   - packages/hwpx_renderer/ 는 코드 보존 (Phase 2/3 재검토 시 참고), 신규 사용 금지.
 *
 * Phase 1 DoD #3 — 와이프 검수용 HWPX 출력. 백엔드가 hwpx_renderer 로 변환한
 * application/hwp+zip 바이트를 받아 a[download] 로 사용자 디스크에 저장.
 *
 * 파일명은 백엔드 Content-Disposition 헤더의 filename 을 그대로 사용한다.
 * 헤더 파싱은 단순 정규식으로 처리 (RFC 5987 enc'ed 처리 미지원 — Phase 1
 * 단일 사용자 환경에서는 ASCII filename 으로 충분).
 *
 * 저장 직후 호출하는 것이 일반적 — 에디터의 미저장 변경이 있으면 호출자가
 * 저장 후 본 함수를 호출해야 한다 (본 함수 자체는 저장 책임 없음).
 */
// ---------------------------------------------------------------------------
// Worksheet API (Stage E2 — 학생 자료 편집 UI)
// ---------------------------------------------------------------------------

/**
 * Worksheet — backend Worksheet 의 TypeScript 미러 (최소 필드).
 * shared/schemas/worksheet.py 가 source of truth. UI 가 사용하는 필드만 선언.
 */
export interface Worksheet {
  id: string;
  title: string;
  subtitle: string | null;
  kind: "student" | "teacher" | "variant";
  template_id: string;
  orientation: "portrait" | "landscape";
  instruction: string | null;
  branding: {
    academy_name?: string | null;
    primary_color?: string | null;
    secondary_color?: string | null;
    logo_url?: string | null;
  };
  school: string | null;
  grade: string | null;
  exam_date: string | null;
  time_limit: string | null;
  items: WorksheetItem[];
  created_at: string;
  updated_at: string;
}

export interface WorksheetItem {
  id: string;
  passage_id: string;
  order: number;
  label: string | null;
  include_translation: boolean;
  include_vocabulary: boolean;
  include_syntax_annotations: boolean;
  include_questions: boolean;
  include_variants: boolean;
}

export interface WorksheetListResponse {
  worksheets: Worksheet[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * listWorksheets — GET /worksheets
 *
 * 목록 조회. 각 Worksheet 의 items 는 빈 리스트 (단건 조회로 별도 가져옴).
 *
 * @param params.limit  1~100 (default 20)
 * @param params.offset >= 0 (default 0)
 * @param params.kind   필터 (선택)
 */
export async function listWorksheets(params?: {
  limit?: number;
  offset?: number;
  kind?: "student" | "teacher" | "variant";
}): Promise<WorksheetListResponse> {
  // FastAPI 라우터의 trailing slash 정책 — `/worksheets/` 명시 (없으면 307 redirect).
  const url = new URL(`${API_BASE_URL}/worksheets/`);
  if (params?.limit != null) url.searchParams.set("limit", String(params.limit));
  if (params?.offset != null) url.searchParams.set("offset", String(params.offset));
  if (params?.kind) url.searchParams.set("kind", params.kind);

  const response = await fetch(url.toString());
  await checkOk(response);
  return (await response.json()) as WorksheetListResponse;
}

/**
 * getWorksheet — GET /worksheets/{id}
 *
 * 단건 조회 (items 포함).
 */
export async function getWorksheet(id: string): Promise<Worksheet> {
  const response = await fetch(`${API_BASE_URL}/worksheets/${id}`);
  await checkOk(response);
  return (await response.json()) as Worksheet;
}

/**
 * downloadWorksheetPdf — POST /worksheets/{id}/export.pdf → 브라우저 다운로드.
 *
 * Content-Disposition: attachment; filename*=UTF-8''<encoded>.pdf 헤더 사용.
 */
export async function downloadWorksheetPdf(worksheetId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/worksheets/${worksheetId}/export.pdf`, {
    method: "POST",
  });
  await checkOk(response);
  const blob = await response.blob();

  // RFC 5987 filename* 추출 시도. 실패 시 fallback.
  const disposition = response.headers.get("content-disposition") ?? "";
  const m5987 = disposition.match(/filename\*=UTF-8''([^;]+)/);
  const mPlain = disposition.match(/filename="([^"]+)"/);
  let filename = `worksheet_${worksheetId}.pdf`;
  if (m5987?.[1]) {
    try {
      filename = decodeURIComponent(m5987[1]);
    } catch {
      // ignore decode error, use fallback
    }
  } else if (mPlain?.[1]) {
    filename = mPlain[1];
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * extractPassageText — POST /passages/extract (kind=text)
 *
 * 텍스트 1건을 정규화된 Passage + Question[] + Translation + Vocabulary 로 변환 + 영속화.
 * PassageNewPage 진입점 — results 전체 반환 (다중 지문 대비).
 *
 * @param payload  영어 지문 (+ 선택적으로 5지선다 + 정답)
 * @param targetGrade  대상 학년 (default "high_3")
 */
export async function extractPassageText(
  payload: string,
  targetGrade?: string
): Promise<ExtractedPassageResult[]> {
  const response = await fetch(`${API_BASE_URL}/passages/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kind: "text",
      payload,
      ...(targetGrade ? { target_grade: targetGrade } : {}),
    }),
  });
  await checkOk(response);
  const body = (await response.json()) as { results: ExtractedPassageResult[] };
  return body.results ?? [];
}

/**
 * extractPassageImage — POST /passages/extract (kind=image)
 *
 * 이미지 파일 (PNG/JPG) → multipart/form-data 로 전송 → Passage + Questions 추출.
 * 다중 이미지 (여러 페이지) 동시 업로드 지원.
 *
 * @param files        PNG/JPG 파일 배열
 * @param targetGrade  대상 학년 (default "high_3")
 */
export async function extractPassageImage(
  files: File[],
  targetGrade?: string
): Promise<ExtractedPassageResult[]> {
  if (files.length === 0) throw new Error("이미지 파일이 없습니다.");

  // 여러 이미지 — 각각 extract 후 합산 (백엔드가 kind=image 는 파일 1개씩 처리)
  const results: ExtractedPassageResult[] = [];
  for (const file of files) {
    const base64 = await _fileToBase64(file);
    // media_type 추론 — JPEG/PNG 만 지원
    const mediaType = file.type === "image/jpeg" ? "image/jpeg" : "image/png";
    const response = await fetch(`${API_BASE_URL}/passages/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind: "image",
        payload: base64,
        media_type: mediaType,
        ...(targetGrade ? { target_grade: targetGrade } : {}),
      }),
    });
    await checkOk(response);
    const body = (await response.json()) as { results: ExtractedPassageResult[] };
    results.push(...(body.results ?? []));
  }
  return results;
}

/**
 * extractPassagePdf — POST /passages/extract (kind=pdf)
 *
 * PDF 파일 → base64 변환 후 전송 → Passage + Questions 추출.
 *
 * @param file         PDF 파일 (1건)
 * @param targetGrade  대상 학년 (default "high_3")
 */
export async function extractPassagePdf(
  file: File,
  targetGrade?: string
): Promise<ExtractedPassageResult[]> {
  const base64 = await _fileToBase64(file);
  const response = await fetch(`${API_BASE_URL}/passages/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kind: "pdf",
      payload: base64,
      ...(targetGrade ? { target_grade: targetGrade } : {}),
    }),
  });
  await checkOk(response);
  const body = (await response.json()) as { results: ExtractedPassageResult[] };
  return body.results ?? [];
}

/**
 * createVariant — POST /questions/{questionId}/variants/{kind}
 *
 * 원본 Question 에서 variant_kind 에 해당하는 변형 문제를 LLM 으로 생성.
 * 생성 직후 qa-validator 가 정답 유일성 검증 (uniqueness_validated 포함 응답).
 *
 * LLM call 2회 (생성 + 검증) — 5~10초 소요 가능.
 *
 * @param questionId   원본 Question ID
 * @param variantKind  VariantKind (snake_case, 경로 파라미터는 kebab-case 로 변환)
 */
export async function createVariant(
  questionId: string,
  variantKind: VariantKind
): Promise<Question> {
  // VariantKind snake_case → API 경로 kebab-case 변환 (예: vocabulary_swap → vocabulary-swap)
  const kindPath = variantKind.replace(/_/g, "-");
  const response = await fetch(`${API_BASE_URL}/questions/${questionId}/variants/${kindPath}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  await checkOk(response);
  return (await response.json()) as Question;
}

/**
 * getCompatibleTypes — GET /questions/{questionId}/compatible-types
 */
export async function getCompatibleTypes(questionId: string): Promise<CompatibleTypeInfo[]> {
  const response = await fetch(`${API_BASE_URL}/questions/${questionId}/compatible-types`);
  await checkOk(response);
  return (await response.json()) as CompatibleTypeInfo[];
}

/**
 * createCrossTypeVariant — POST /questions/{questionId}/variants
 */
export async function createCrossTypeVariant(
  questionId: string,
  targetType: string
): Promise<Question> {
  const response = await fetch(`${API_BASE_URL}/questions/${questionId}/variants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_type: targetType }),
  });
  await checkOk(response);
  return (await response.json()) as Question;
}

// ---------------------------------------------------------------------------
// 내부 헬퍼 — 파일 → Base64
// ---------------------------------------------------------------------------

/**
 * _fileToBase64 — File/Blob 을 base64 문자열로 변환 (data: prefix 제외).
 */
function _fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // "data:<mime>;base64,<data>" 에서 data 부분만 추출
      const base64 = result.split(",")[1];
      if (base64 == null) {
        reject(new Error("FileReader 결과가 비어있습니다."));
      } else {
        resolve(base64);
      }
    };
    reader.onerror = () => reject(reader.error ?? new Error("파일 읽기 실패"));
    reader.readAsDataURL(file);
  });
}

export interface WorksheetCreateInput {
  title: string;
  subtitle?: string | null;
  kind: "student" | "teacher" | "variant";
  template_id: string;
  orientation?: "portrait" | "landscape";
  instruction?: string | null;
  branding?: {
    academy_name?: string | null;
    primary_color?: string | null;
    secondary_color?: string | null;
    logo_url?: string | null;
  };
  items: Array<{
    passage_id: string;
    order: number;
    label?: string | null;
    include_translation?: boolean;
    include_vocabulary?: boolean;
    include_syntax_annotations?: boolean;
    include_questions?: boolean;
    include_variants?: boolean;
  }>;
}

/**
 * createWorksheet — POST /worksheets/
 *
 * 신규 Worksheet 생성. trailing slash 명시 (FastAPI 307 redirect 회피).
 */
export async function createWorksheet(input: WorksheetCreateInput): Promise<Worksheet> {
  const response = await fetch(`${API_BASE_URL}/worksheets/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  await checkOk(response);
  return (await response.json()) as Worksheet;
}

/**
 * WorksheetMetaPatchInput — PATCH /worksheets/{id} 입력 (Stage E2-3d).
 *
 * 모든 필드 optional (보낸 키만 변경). branding 은 통째 교체 (부분 patch 미지원).
 * NOT NULL 필드 (title / kind / template_id / orientation) 에 ``null`` 명시 →
 * 백엔드 422 (W-1 차단).
 *
 * "변경하지 않음" 을 표현하려면 키 자체를 *제외*. ``undefined`` 는 fetch body
 * 직렬화 시 자동 제외됨.
 */
export interface WorksheetMetaPatchInput {
  title?: string;
  subtitle?: string | null;
  kind?: "student" | "teacher" | "variant";
  template_id?: string;
  orientation?: "portrait" | "landscape";
  instruction?: string | null;
  branding?: {
    academy_name?: string | null;
    primary_color?: string | null;
    secondary_color?: string | null;
    logo_url?: string | null;
  } | null;
  school?: string | null;
  grade?: string | null;
  exam_date?: string | null;
  time_limit?: string | null;
}

/**
 * patchWorksheet — PATCH /worksheets/{id}
 *
 * Worksheet 메타 부분 수정. 빈 patch ({}) 는 백엔드 422.
 * items 변경은 별 라우트 (POST/PATCH/DELETE /worksheets/{id}/items).
 */
export async function patchWorksheet(
  worksheetId: string,
  patch: WorksheetMetaPatchInput
): Promise<Worksheet> {
  const response = await fetch(`${API_BASE_URL}/worksheets/${worksheetId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  await checkOk(response);
  return (await response.json()) as Worksheet;
}

// ---------------------------------------------------------------------------
// Worksheet Items API (Stage E2-3e — items 추가 / 수정 / 삭제 / 순서 변경)
// ---------------------------------------------------------------------------

/**
 * WorksheetItemCreateInput — POST /worksheets/{id}/items 입력.
 *
 * passage_id 와 order 는 필수 (백엔드 ge=0).
 * include_* 플래그는 default false.
 */
export interface WorksheetItemCreateInput {
  passage_id: string;
  order: number;
  label?: string | null;
  include_translation?: boolean;
  include_vocabulary?: boolean;
  include_syntax_annotations?: boolean;
  include_questions?: boolean;
  include_variants?: boolean;
}

/**
 * WorksheetItemPatchInput — PATCH /worksheets/{id}/items/{item_id} 입력.
 *
 * 모든 필드 optional. 보낸 키만 변경된다 (백엔드 exclude_unset).
 * passage_id 는 변경 불가 (extra="forbid" 422). 변경하려면 DELETE + POST.
 */
export interface WorksheetItemPatchInput {
  order?: number;
  label?: string | null;
  include_translation?: boolean;
  include_vocabulary?: boolean;
  include_syntax_annotations?: boolean;
  include_questions?: boolean;
  include_variants?: boolean;
}

/**
 * addWorksheetItem — POST /worksheets/{worksheetId}/items
 *
 * 기존 Worksheet 에 item 1개 추가. 같은 passage_id 가 이미 존재하면 422.
 */
export async function addWorksheetItem(
  worksheetId: string,
  input: WorksheetItemCreateInput
): Promise<WorksheetItem> {
  const response = await fetch(`${API_BASE_URL}/worksheets/${worksheetId}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  await checkOk(response);
  return (await response.json()) as WorksheetItem;
}

/**
 * patchWorksheetItem — PATCH /worksheets/{worksheetId}/items/{itemId}
 *
 * item 부분 수정 (order / label / include_* 플래그). 빈 patch ({}) → 422.
 */
export async function patchWorksheetItem(
  worksheetId: string,
  itemId: string,
  patch: WorksheetItemPatchInput
): Promise<WorksheetItem> {
  const response = await fetch(`${API_BASE_URL}/worksheets/${worksheetId}/items/${itemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  await checkOk(response);
  return (await response.json()) as WorksheetItem;
}

/**
 * deleteWorksheetItem — DELETE /worksheets/{worksheetId}/items/{itemId}
 *
 * item 1개 삭제. 204 응답.
 */
export async function deleteWorksheetItem(worksheetId: string, itemId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/worksheets/${worksheetId}/items/${itemId}`, {
    method: "DELETE",
  });
  await checkOk(response);
}

export async function downloadPassageHwpx(passageId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/passages/${passageId}/hwpx`);
  await checkOk(response);

  const blob = await response.blob();

  // Content-Disposition 의 filename 추출. 실패 시 fallback.
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? `passage_${passageId}.hwpx`;

  // a[download] 트리거 — DOM 임시 element + URL.revokeObjectURL 정리.
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
