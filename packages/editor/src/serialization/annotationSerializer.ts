/**
 * annotationSerializer — ProseMirror doc ↔ SyntaxAnnotation[] 양방향 변환.
 *
 * ADR-0004 결정 (character offset + ProseMirror position 하이브리드) 을 구현한다.
 * - 직렬화 (docToAnnotations): Tiptap doc JSON → SerializedAnnotation[]
 *   - ProseMirror 트리를 순회하며 텍스트 노드 길이를 누적 → character offset 계산
 *   - 에디터 메모 (EditorPoc.tsx): "mark range 는 text 노드 분리 방식으로 표현됨"
 * - 역직렬화 (annotationsToMarks): SerializedAnnotation[] → mark 적용 명령 목록
 *   - character offset → ProseMirror position 변환 (pmPosFromCharOffset)
 *
 * 이 모듈이 다루는 직렬화 계약 (v0.2 — P1-3, ADR-0004 적용 후):
 *   - span: { span_format: "character_offset_v1", start, end }  (평탄 구조)
 *   - arrow_target_span: 동일 구조, kind == "arrow" 일 때만 (Python 측에서
 *     model validator 로 강제 — kind == arrow ↔ arrow_target_span is not None).
 */

import type { JSONContent } from "@tiptap/core";
import {
  ANNOTATION_KIND,
  type AnnotationKind,
  KIND_TO_MARK_NAME,
  MARK_NAME_TO_KIND,
} from "../extensions/annotationKind";

// ---------------------------------------------------------------------------
// 타입 정의 (공개 API)
// ---------------------------------------------------------------------------

/**
 * CharacterOffsetV1Span — shared/schemas/annotation.py CharacterOffsetV1Span v0.2 미러.
 *
 * P1-3 (ADR-0004 적용): v0.1 placeholder 의 `data: {start, end}` 가
 * `start, end` 1급 필드로 승격됐다.
 */
export interface CharacterOffsetV1Span {
  span_format: "character_offset_v1";
  start: number;
  end: number;
}

/**
 * AnnotationSpan — Python AnnotationSpan discriminated union 미러.
 *
 * v0.2 는 단일 멤버 union (CharacterOffsetV1Span). 미래 확장 시 union 멤버
 * 추가만으로 대응 가능 — span_format 디스크리미네이터로 분기.
 */
export type AnnotationSpanV1 = CharacterOffsetV1Span;

/**
 * SerializedAnnotation — SyntaxAnnotation 의 TypeScript 직렬화 표현.
 *
 * Python SyntaxAnnotation 과 1:1 대응. passage_id / id / tenant_id 는
 * 에디터 레이어에서 알 수 없으므로 optional — API 저장 시 채워진다.
 *
 * 이 타입은 "에디터 → 백엔드" 방향의 직렬화 출력이다.
 *
 * P1-2b: annotation_id 필드 추가 — 에디터 측 UUID. 클라이언트 칩 식별에 사용.
 * optional (기존 데이터 / 테스트 호환 유지).
 */
export interface SerializedAnnotation {
  kind: AnnotationKind;
  span: AnnotationSpanV1;
  color_index?: number | null;
  text?: string | null;
  bracket_style?: "()" | "{}" | "[]" | null;
  arrow_target_span?: AnnotationSpanV1 | null;
  category?: string | null;
  annotation_id?: string | null;
}

/**
 * MarkAttrs — 역직렬화 시 Tiptap setMark 에 전달할 mark 정보.
 *
 * annotationsToMarks 의 출력 아이템. from/to 는 ProseMirror position (1-based).
 * 실제 적용은 호출자 (에디터 컴포넌트) 의 책임.
 */
export interface MarkAttrs {
  kind: AnnotationKind;
  markName: string;
  from: number; // ProseMirror position (inclusive)
  to: number; // ProseMirror position (exclusive)
  attrs: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// 내부 헬퍼
// ---------------------------------------------------------------------------

/**
 * ProseMirror doc 트리를 DFS 순회하며 각 mark 의 character offset 을 수집한다.
 *
 * EditorPoc.tsx 메모: "mark range 는 text 노드 분리 방식으로 표현됨. 절대
 * character offset 은 트리 순회하며 텍스트 노드 길이 누적으로 복원 가능."
 *
 * 반환: { markName, attrs, charStart, charEnd }[]
 * charStart / charEnd 는 Passage.body_text 위 [start, end) 반열린 구간.
 *
 * 구현 전략:
 *   ProseMirror doc JSON 의 노드는 content[] 로 중첩된다.
 *   텍스트 노드 (type == "text") 만 실제 글자가 있다.
 *   charOffset 을 누적하며 순회 — text 노드를 만나면:
 *     - marks[] 가 있으면 각 mark 에 대해 [charOffset, charOffset + text.length) 기록
 *     - charOffset += text.length
 *   단락 / 제목 / 기타 블록 노드는 글자 없이 자식만 순회.
 *
 * 제약:
 *   - paragraph 노드 경계는 현재 char offset 계산에 포함하지 않는다.
 *     즉 여러 단락이 있으면 단락 경계(\n) 가 body_text 에 있는지 여부에 따라
 *     offset 이 달라질 수 있다. Phase 1 v0.1 에서는 단일 단락 지문 가정.
 *     복수 단락 케이스는 P1-3 에서 Passage.body_text 정규화 정책과 함께 처리.
 */
interface CollectedMark {
  markName: string;
  attrs: Record<string, unknown>;
  charStart: number;
  charEnd: number;
}

function collectMarksFromDoc(doc: JSONContent): CollectedMark[] {
  const collected: CollectedMark[] = [];
  let charOffset = 0;

  function traverse(node: JSONContent): void {
    if (node.type === "text") {
      const text = node.text ?? "";
      const len = text.length;
      if (node.marks && node.marks.length > 0) {
        for (const mark of node.marks) {
          if (!mark.type) continue;
          collected.push({
            markName: mark.type,
            attrs: (mark.attrs as Record<string, unknown>) ?? {},
            charStart: charOffset,
            charEnd: charOffset + len,
          });
        }
      }
      charOffset += len;
    } else if (node.content) {
      for (const child of node.content) {
        traverse(child);
      }
    }
  }

  traverse(doc);
  return collected;
}

/**
 * character offset → ProseMirror position 변환.
 *
 * ADR-0004 §결정: "Tiptap 에디터 내부: ProseMirror position (from, to) 로 작업."
 *
 * ProseMirror doc 에서 position 은 노드 경계 포함 1-based 카운트다.
 * 텍스트 노드 내 글자 위치 = 노드 시작 position + 텍스트 내 index.
 * 단락 노드 자체가 position 1개를 차지하므로, 첫 단락 시작 = pos 1 + 1(단락 열기) = 2.
 *
 * 단순화 가정 (v0.1, 단일 단락):
 *   - doc (pos 0) → paragraph (pos 1) → 텍스트 시작 (pos 2)
 *   - charOffset k → pmPos = k + 2 (단락 1개 기준)
 *
 * 단일 단락 가정 v0.1. 다중 단락 정책은 P1-2 (인터랙션 UI) 또는 P1-5 (DB API) 진입 시
 * 별도 follow-up 으로 결정 — 본 함수 + ``pmPosToCharOffset`` + ``AnnotationSpanV1``
 * 생성 사이트 모두 동시 갱신 필요.
 */
function charOffsetToPmPos(charOffset: number): number {
  // 단락 열기 노드(pos 0=doc, pos 1=paragraph open) + 글자 위치
  // 단일 단락 단순화: pmPos = charOffset + 2
  return charOffset + 2;
}

/**
 * ProseMirror position → character offset 변환 (역방향).
 *
 * charOffsetToPmPos 의 역함수.
 */
function pmPosToCharOffset(pmPos: number): number {
  return pmPos - 2;
}

// ---------------------------------------------------------------------------
// 공개 API
// ---------------------------------------------------------------------------

/**
 * docToAnnotations — Tiptap doc JSON → SerializedAnnotation[] 직렬화.
 *
 * 사용법:
 *   const json = editor.getJSON();
 *   const annotations = docToAnnotations(json);
 *   // annotations 를 API POST /passages/:id/annotations 에 전달
 *
 * MARK_NAME_TO_KIND 에 없는 mark 는 무시한다 (예: StarterKit 의 bold/italic).
 */
export function docToAnnotations(doc: JSONContent): SerializedAnnotation[] {
  const rawMarks = collectMarksFromDoc(doc);
  const result: SerializedAnnotation[] = [];

  for (const raw of rawMarks) {
    const kind = MARK_NAME_TO_KIND[raw.markName];
    if (!kind) continue; // StarterKit mark 등 무시

    const span: AnnotationSpanV1 = {
      span_format: "character_offset_v1",
      start: raw.charStart,
      end: raw.charEnd,
    };

    const annotation: SerializedAnnotation = {
      kind,
      span,
    };

    // kind-specific attrs 추출
    if (
      kind === ANNOTATION_KIND.TOP_LABEL ||
      kind === ANNOTATION_KIND.BOTTOM_LABEL ||
      kind === ANNOTATION_KIND.INLINE_NOTE
    ) {
      annotation.text = (raw.attrs.text as string | null | undefined) ?? null;
    }

    if (kind === ANNOTATION_KIND.BRACKET) {
      annotation.bracket_style =
        (raw.attrs.bracketStyle as "()" | "{}" | "[]" | null | undefined) ?? null;
    }

    if (kind === ANNOTATION_KIND.ARROW) {
      const targetStart = raw.attrs.arrowTargetStart as number | null | undefined;
      const targetEnd = raw.attrs.arrowTargetEnd as number | null | undefined;
      if (targetStart != null && targetEnd != null) {
        annotation.arrow_target_span = {
          span_format: "character_offset_v1",
          start: targetStart,
          end: targetEnd,
        };
      } else {
        // arrow_target_span 이 null 이면 백엔드 ValidationError 발생. drop 하고 경고.
        console.warn(
          "[annotationSerializer] ARROW mark 에 arrowTargetStart/arrowTargetEnd 가 없어 annotation 을 제외합니다.",
          { charStart: raw.charStart, charEnd: raw.charEnd, attrs: raw.attrs }
        );
        continue;
      }
    }

    const colorIndex = raw.attrs.colorIndex as number | null | undefined;
    if (colorIndex != null) {
      annotation.color_index = colorIndex;
    }

    // highlight 의 color 속성 처리 (@tiptap/extension-highlight 가 "color" attr 사용)
    if (kind === ANNOTATION_KIND.HIGHLIGHT) {
      const color = raw.attrs.color as string | null | undefined;
      if (color) {
        // color 는 hex string — color_index 로 매핑은 P1-3 에서 팔레트 확정 후.
        // v0.1 에서는 color 를 별도 보존하지 않고 color_index 만 기록.
        // 현재는 color_index 없이 저장 (null).
      }
    }

    // category — 선택적 분류 필드. 모든 kind 에 공통. mark spec 에 category attrs 가
    // 있는 경우에만 추출 (highlight/underline 공식 extension 은 category 미지원).
    const category = raw.attrs.category as string | null | undefined;
    if (category != null) {
      annotation.category = category;
    }

    // annotation_id — P1-2b: 에디터 측 UUID. mark attrs 의 annotationId 를 그대로 직렬화.
    const annotationId = raw.attrs.annotationId as string | null | undefined;
    if (annotationId != null) {
      annotation.annotation_id = annotationId;
    }

    result.push(annotation);
  }

  return result;
}

/**
 * annotationsToMarks — SerializedAnnotation[] → MarkAttrs[] 역직렬화.
 *
 * DB / API 에서 받은 SyntaxAnnotation[] 을 Tiptap editor 에 적용할 mark 목록으로
 * 변환한다. 실제 적용은 호출자 (에디터 컴포넌트) 책임:
 *
 *   const marks = annotationsToMarks(annotations);
 *   for (const m of marks) {
 *     editor
 *       .chain()
 *       .setTextSelection({ from: m.from, to: m.to })
 *       .setMark(m.markName, m.attrs)
 *       .run();
 *   }
 *
 * character offset → ProseMirror position 변환 (charOffsetToPmPos) 포함.
 * v0.1 단순화: 단일 단락 가정. 다중 단락은 P1-3 에서 처리.
 *
 * KIND_TO_MARK_NAME 에 없는 kind 는 무시한다 (미래 확장 대비).
 */
export function annotationsToMarks(annotations: SerializedAnnotation[]): MarkAttrs[] {
  const result: MarkAttrs[] = [];

  for (const ann of annotations) {
    const from = charOffsetToPmPos(ann.span.start);
    const to = charOffsetToPmPos(ann.span.end);

    const attrs: Record<string, unknown> = {};

    if (ann.text != null) {
      attrs.text = ann.text;
    }
    if (ann.color_index != null) {
      attrs.colorIndex = ann.color_index;
    }
    if (ann.bracket_style != null) {
      attrs.bracketStyle = ann.bracket_style;
    }
    if (ann.arrow_target_span != null) {
      attrs.arrowTargetStart = ann.arrow_target_span.start;
      attrs.arrowTargetEnd = ann.arrow_target_span.end;
    }
    if (ann.category != null) {
      attrs.category = ann.category;
    }
    if (ann.annotation_id != null) {
      attrs.annotationId = ann.annotation_id;
    }

    result.push({
      kind: ann.kind,
      markName: KIND_TO_MARK_NAME[ann.kind] ?? ann.kind,
      from,
      to,
      attrs,
    });
  }

  return result;
}

// 변환 헬퍼 export (테스트 + 에디터 컴포넌트 직접 사용용)
export { charOffsetToPmPos, pmPosToCharOffset };
