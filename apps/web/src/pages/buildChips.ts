/**
 * buildChips — editor doc → AnnotationChip[] 변환 유틸 (P1-2c follow-up)
 *
 * EditorPoc 에서 분리: annotationId 기반 dedup + KIND_PRIORITY 우선순위 로직을
 * 단독으로 테스트 가능하게 만들기 위함.
 *
 * 사용처: EditorPoc.tsx
 */

import { docToAnnotations } from "@english-worksheet-tool/editor";
import type { AnnotationChip } from "../components/AnalysisTable";

// ---------------------------------------------------------------------------
// 상수
// ---------------------------------------------------------------------------

/**
 * KIND_PRIORITY — annotationId 공유 시 칩 대표 mark 우선순위.
 *
 * 같은 annotationId 의 mark 가 여러 개일 때 (예: top_label + bracket 공유),
 * text attrs 가 있는 라벨 mark 가 칩 대표가 되도록 우선순위를 부여한다.
 * 낮은 숫자 = 더 높은 우선순위.
 *
 * 우선순위: top_label > bottom_label > inline_note > bracket > arrow > underline > highlight
 */
export const KIND_PRIORITY: Record<string, number> = {
  top_label: 0,
  bottom_label: 1,
  inline_note: 2,
  bracket: 3,
  arrow: 4,
  underline: 5,
  highlight: 6,
};

export function kindPriority(kind: string): number {
  return KIND_PRIORITY[kind] ?? 99;
}

// ---------------------------------------------------------------------------
// 헬퍼
// ---------------------------------------------------------------------------

/**
 * extractDocText — ProseMirror JSON 의 모든 text 노드를 순회해 본문을 단락 사이
 * "\n" 으로 잇는다. annotationSerializer 의 charOffset 계산 규칙과 동일해야
 * span.start / span.end 가 본문 인덱스로 일치한다.
 */
// JsonDoc — JSONContent の代わりに独自型 (apps/web は @tiptap/core を直接依存しないため)
type JsonDoc = { content?: unknown[] };

export function extractDocText(doc: JsonDoc): string {
  if (!doc || !Array.isArray(doc.content)) return "";
  const paragraphs: string[] = [];

  type JsonNode = { type?: string; text?: string; content?: JsonNode[] };

  function paragraphText(node: JsonNode): string {
    if (!node.content) return "";
    let s = "";
    for (const child of node.content) {
      if (child.type === "text") s += child.text ?? "";
    }
    return s;
  }

  for (const node of doc.content as JsonNode[]) {
    if (node.type === "paragraph") paragraphs.push(paragraphText(node));
  }
  return paragraphs.join("\n");
}

/**
 * truncate — 30자 초과 시 양 끝 살리고 가운데 ... 처리.
 */
export function truncate(s: string, max = 30): string {
  if (s.length <= max) return s;
  const head = Math.ceil((max - 1) / 2);
  const tail = Math.floor((max - 1) / 2);
  return `${s.slice(0, head)}…${s.slice(s.length - tail)}`;
}

// ---------------------------------------------------------------------------
// highlight hex 추출 헬퍼 (C-2b — 자유색상 chip 동기화)
// ---------------------------------------------------------------------------

/**
 * extractHighlightHexMap — ProseMirror doc JSON 에서
 * annotationId → mark.attrs.color hex 매핑을 추출한다.
 *
 * highlight mark 의 `color` attr 은 EditorPoc 에서 실제 hex 를 직접 주입한 것
 * (colorIndex 팔레트 or 자유색상 picker). SerializedAnnotation 은 color_index 만
 * 직렬화하므로, 자유색상(팔레트 외 hex)이 chip 에 반영되려면 doc JSON 에서 직접 읽어야 한다.
 *
 * PM 결정 1 — 구현 방식 C: mark.attrs.color hex 를 chip 컴포넌트가 직접 읽어 적용.
 * schema 변경 없음.
 */
type JsonNode = { type?: string; text?: string; marks?: JsonMark[]; content?: JsonNode[] };
type JsonMark = { type?: string; attrs?: Record<string, unknown> };

export function extractHighlightHexMap(doc: JsonDoc): Map<string, string> {
  const hexMap = new Map<string, string>();

  function walk(node: JsonNode): void {
    if (node.type === "text" && node.marks) {
      for (const mark of node.marks) {
        if (mark.type !== "highlight") continue;
        const attrs = mark.attrs ?? {};
        const annId = attrs.annotationId as string | null | undefined;
        const color = attrs.color as string | null | undefined;
        if (annId && color && !hexMap.has(annId)) {
          hexMap.set(annId, color);
        }
      }
    }
    if (node.content) {
      for (const child of node.content as JsonNode[]) {
        walk(child);
      }
    }
  }

  walk(doc as JsonNode);
  return hexMap;
}

// ---------------------------------------------------------------------------
// 핵심 함수
// ---------------------------------------------------------------------------

/**
 * buildChips — editor.getJSON() doc 을 docToAnnotations 로 파싱 후
 * annotationId 별로 dedup 해서 AnnotationChip[] 로 변환한다.
 *
 * 같은 annotationId 의 mark 가 여러 개일 때 (예: top_label + bracket 공유):
 *   - KIND_PRIORITY 순으로 대표 mark 를 선택 (top_label > bottom_label > inline_note > bracket > ...)
 *   - bracket mark 는 대표가 아니더라도 bracketStyle 필드로 칩에 보존
 * spanText 는 본문에서 character offset 으로 slice 한 실제 텍스트 (30자 줄임).
 *
 * C-2b: highlight kind 칩에 highlightHex 필드 추가 — mark.attrs.color hex 를 직접 주입.
 * 자유색상(팔레트 외 hex)이 chip 배경에 바로 반영된다 (PM 결정 1, 구현 방식 C).
 */
export function buildChips(doc: JsonDoc): AnnotationChip[] {
  // biome-ignore lint/suspicious/noExplicitAny: apps/web 은 @tiptap/core 직접 의존 없음 — JSONContent 대신 JsonDoc 사용, 캐스트 불가피
  const annotations = docToAnnotations(doc as any);
  const bodyText = extractDocText(doc);

  // C-2b: highlight hex 사전 수집
  const highlightHexMap = extractHighlightHexMap(doc);

  // id → { chip, priority } 를 관리 (우선순위 높은 mark 로 교체)
  const chipMap = new Map<string, { chip: AnnotationChip; priority: number }>();

  for (const ann of annotations) {
    const id = ann.annotation_id ?? `${ann.kind}:${ann.span.start}-${ann.span.end}`;
    const prio = kindPriority(ann.kind);

    const rawSpan = bodyText.slice(ann.span.start, ann.span.end);
    const spanText = truncate(rawSpan);
    const labelText =
      ann.kind === "top_label" || ann.kind === "bottom_label" || ann.kind === "inline_note"
        ? (ann.text ?? "")
        : "";

    // C-2b: highlight hex — annotationId 로 doc 에서 직접 추출
    const highlightHex = ann.kind === "highlight" ? (highlightHexMap.get(id) ?? null) : undefined;

    const existing = chipMap.get(id);

    if (!existing) {
      chipMap.set(id, {
        chip: {
          annotationId: id,
          kind: ann.kind,
          category: ann.category ?? null,
          colorIndex: ann.color_index ?? null,
          labelText,
          spanText,
          bracketStyle: ann.kind === "bracket" ? (ann.bracket_style ?? null) : null,
          ...(ann.kind === "highlight" ? { highlightHex } : {}),
        },
        priority: prio,
      });
    } else {
      // bracket mark 가 기존에 없고 현재 ann 이 bracket 이면 bracketStyle 을 기존 칩에 주입
      if (ann.kind === "bracket" && existing.chip.bracketStyle == null) {
        existing.chip.bracketStyle = ann.bracket_style ?? null;
      }

      // 현재 ann 의 우선순위가 기존보다 높으면 대표 mark 교체 (bracketStyle 은 유지)
      if (prio < existing.priority) {
        const prevBracketStyle = existing.chip.bracketStyle;
        chipMap.set(id, {
          chip: {
            annotationId: id,
            kind: ann.kind,
            category: ann.category ?? null,
            colorIndex: ann.color_index ?? null,
            labelText,
            spanText,
            bracketStyle: prevBracketStyle, // 기존 bracket 정보 유지
            ...(ann.kind === "highlight" ? { highlightHex } : {}),
          },
          priority: prio,
        });
      }
    }
  }

  return Array.from(chipMap.values()).map((v) => v.chip);
}
