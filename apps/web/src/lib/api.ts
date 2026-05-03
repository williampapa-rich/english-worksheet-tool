/**
 * api.ts — backend REST API 클라이언트 (P1-6)
 *
 * fetch 직접 사용. axios 등 라이브러리 없음.
 * VITE_API_BASE_URL 환경변수 없으면 http://localhost:8000 으로 fallback.
 *
 * 함수:
 *   - getPassage(id) — GET /passages/{id}
 *   - getAnnotations(passageId) — GET /passages/{id}/annotations → annotations[]
 *   - replaceAnnotations(passageId, annotations) — POST /passages/{id}/annotations
 */

import type { SerializedAnnotation } from "@english-worksheet-tool/editor";

// ---------------------------------------------------------------------------
// 설정
// ---------------------------------------------------------------------------

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// 도메인 타입 — backend SyntaxAnnotation / Passage 최소 인터페이스
// (full schema 는 shared/schemas/annotation.py 가 source of truth)
// ---------------------------------------------------------------------------

/** Passage — GET /passages/{id} 응답의 최소 필드 */
export interface Passage {
  id: string;
  body_text: string;
  paragraphs?: string[] | null;
  title?: string | null;
  source_material?: string | null;
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
 * 지문 정보 (body_text, paragraphs 등) 를 반환한다.
 */
export async function getPassage(id: string): Promise<Passage> {
  const response = await fetch(`${API_BASE_URL}/passages/${id}`);
  await checkOk(response);
  return (await response.json()) as Passage;
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
