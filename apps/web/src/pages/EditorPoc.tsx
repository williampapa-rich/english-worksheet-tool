import {
  ArrowMark,
  BottomLabelMark,
  BracketMark,
  HighlightMark,
  InlineNoteMark,
  TopLabelMark,
  UnderlineMark,
  WordSnapExtension,
  collectMarkRangesByAnnotationId,
  docToAnnotations,
} from "@english-worksheet-tool/editor";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AnalysisTable, type AnnotationChip } from "../components/AnalysisTable";
import "./EditorPoc.css";

/**
 * EditorPoc — P1-2b 분석표 + annotationId 에디터
 *
 * 목표: annotationId 기반 칩 통째 삭제로 "부분 unset 잔여 마크 버그" 해결.
 * 분석표를 본문 에디터 하단에 배치. 칩 x = 같은 annotationId 의 모든 range unset.
 *
 * 변경 (vs P1-2a):
 *   - 7종 annotation 적용 버튼이 crypto.randomUUID() 로 annotationId 생성 후 주입
 *   - editor.on('update') 로 doc 변경 감지 → chips 상태 갱신
 *   - AnalysisTable + handleRemoveAnnotation 추가
 *   - 기존 JSON 패널 / 12색 picker / category select 그대로 유지
 *
 * 비DoD: API 통합, HWPX 다운로드, 컨텍스트 메뉴, 칩 클릭 강조.
 */

// ---------------------------------------------------------------------------
// 상수
// ---------------------------------------------------------------------------

const EXTENSIONS = [
  StarterKit,
  HighlightMark,
  UnderlineMark,
  TopLabelMark,
  BottomLabelMark,
  BracketMark,
  InlineNoteMark,
  ArrowMark,
  WordSnapExtension,
];

const INITIAL_CONTENT =
  "<p>The student who had studied hard for the exam passed with an excellent score, which made her parents extremely proud.</p><p>Scientists have discovered that regular exercise significantly improves cognitive function and helps prevent age-related memory decline.</p>";

const COLOR_PALETTE: Array<{ index: number; hex: string; label: string }> = [
  { index: 1, hex: "#fef08a", label: "yellow" },
  { index: 2, hex: "#86efac", label: "green" },
  { index: 3, hex: "#93c5fd", label: "blue" },
  { index: 4, hex: "#f9a8d4", label: "pink" },
  { index: 5, hex: "#fdba74", label: "orange" },
  { index: 6, hex: "#c4b5fd", label: "violet" },
  { index: 7, hex: "#6ee7b7", label: "emerald" },
  { index: 8, hex: "#fca5a5", label: "red" },
  { index: 9, hex: "#67e8f9", label: "cyan" },
  { index: 10, hex: "#d9f99d", label: "lime" },
  { index: 11, hex: "#fde68a", label: "amber" },
  { index: 12, hex: "#e9d5ff", label: "purple" },
];

const CATEGORY_OPTIONS = [
  { value: "", label: "category 없음" },
  { value: "note", label: "note" },
  { value: "sentence_role", label: "sentence_role" },
  { value: "phrase", label: "phrase" },
  { value: "clause", label: "clause" },
  { value: "other", label: "other" },
];

// ---------------------------------------------------------------------------
// 헬퍼 — doc 에서 AnnotationChip[] 추출
// ---------------------------------------------------------------------------

/**
 * extractDocText — ProseMirror JSON 의 모든 text 노드를 순회해 본문을 단락 사이
 * "\n" 으로 잇는다. annotationSerializer 의 charOffset 계산 규칙과 동일해야
 * span.start / span.end 가 본문 인덱스로 일치한다.
 */
function extractDocText(
  doc: ReturnType<NonNullable<ReturnType<typeof useEditor>>["getJSON"]>
): string {
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
function truncate(s: string, max = 30): string {
  if (s.length <= max) return s;
  const head = Math.ceil((max - 1) / 2);
  const tail = Math.floor((max - 1) / 2);
  return `${s.slice(0, head)}…${s.slice(s.length - tail)}`;
}

/**
 * buildChips — editor.getJSON() doc 을 docToAnnotations 로 파싱 후
 * annotationId 별로 dedup 해서 AnnotationChip[] 로 변환한다.
 *
 * 같은 annotationId 의 split 조각은 첫 조각만 칩으로 표기한다 (dedup).
 * spanText 는 본문에서 character offset 으로 slice 한 실제 텍스트 (30자 줄임).
 */
function buildChips(
  doc: ReturnType<NonNullable<ReturnType<typeof useEditor>>["getJSON"]>
): AnnotationChip[] {
  const annotations = docToAnnotations(doc);
  const bodyText = extractDocText(doc);
  const seen = new Map<string, AnnotationChip>();

  for (const ann of annotations) {
    // annotationId 없는 기존 annotation — uuid 없이 kind+span 으로 임시 키
    const id = ann.annotation_id ?? `${ann.kind}:${ann.span.start}-${ann.span.end}`;

    if (seen.has(id)) continue; // dedup

    const labelText =
      ann.kind === "top_label" || ann.kind === "bottom_label" || ann.kind === "inline_note"
        ? (ann.text ?? "")
        : "";

    const rawSpan = bodyText.slice(ann.span.start, ann.span.end);
    const spanText = truncate(rawSpan);

    seen.set(id, {
      annotationId: id,
      kind: ann.kind,
      category: ann.category ?? null,
      colorIndex: ann.color_index ?? null,
      labelText,
      spanText,
    });
  }

  return Array.from(seen.values());
}

// ---------------------------------------------------------------------------
// 컴포넌트
// ---------------------------------------------------------------------------

export function EditorPoc() {
  const [selectedColorIndex, setSelectedColorIndex] = useState<number>(1);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [serializedJson, setSerializedJson] = useState<string | null>(null);
  const [chips, setChips] = useState<AnnotationChip[]>([]);

  const editor = useEditor({
    extensions: EXTENSIONS,
    content: INITIAL_CONTENT,
    editorProps: {
      attributes: {
        class: "min-h-[160px] p-4 focus:outline-none prose prose-sm max-w-none",
      },
    },
  });

  // doc 변경 감지 → chips 갱신
  useEffect(() => {
    if (!editor) return;
    const updateChips = () => {
      const doc = editor.getJSON();
      setChips(buildChips(doc));
    };
    editor.on("update", updateChips);
    updateChips(); // 초기 실행
    return () => {
      editor.off("update", updateChips);
    };
  }, [editor]);

  // ---------------------------------------------------------------------------
  // 핸들러 — annotation 적용 (annotationId 주입)
  // ---------------------------------------------------------------------------

  const handleHighlight = () => {
    if (!editor) return;
    const palette = COLOR_PALETTE.find((c) => c.index === selectedColorIndex);
    const color = palette?.hex ?? "#fef08a";
    const annotationId = crypto.randomUUID();
    editor.chain().focus().setMark("highlight", { color, annotationId }).run();
  };

  const handleUnderline = () => {
    if (!editor) return;
    const annotationId = crypto.randomUUID();
    editor.chain().focus().setMark("underline", { annotationId }).run();
  };

  const handleTopLabel = () => {
    if (!editor) return;
    const text = prompt("상단 라벨 텍스트를 입력하세요 (예: S, V, 관계절):");
    if (!text) return;
    const annotationId = crypto.randomUUID();
    editor
      .chain()
      .focus()
      .setTopLabel({
        text,
        colorIndex: selectedColorIndex,
        category: selectedCategory || null,
        annotationId,
      })
      .run();
  };

  const handleBottomLabel = () => {
    if (!editor) return;
    const text = prompt("하단 라벨 텍스트를 입력하세요 (예: S, V, O):");
    if (!text) return;
    const annotationId = crypto.randomUUID();
    editor
      .chain()
      .focus()
      .setBottomLabel({
        text,
        colorIndex: selectedColorIndex,
        category: selectedCategory || null,
        annotationId,
      })
      .run();
  };

  const handleBracket = () => {
    if (!editor) return;
    const style = prompt("괄호 스타일 선택: () / {} / []", "()");
    if (!style || !["()", "{}", "[]"].includes(style)) return;
    const annotationId = crypto.randomUUID();
    editor
      .chain()
      .focus()
      .setBracket({
        bracketStyle: style as "()" | "{}" | "[]",
        colorIndex: selectedColorIndex,
        category: selectedCategory || null,
        annotationId,
      })
      .run();
  };

  const handleArrow = () => {
    if (!editor) return;
    const targetStartStr = prompt("화살표 도착점 시작 offset (숫자):");
    const targetEndStr = prompt("화살표 도착점 끝 offset (숫자):");
    const targetStart = Number(targetStartStr);
    const targetEnd = Number(targetEndStr);
    if (Number.isNaN(targetStart) || Number.isNaN(targetEnd) || targetStart >= targetEnd) {
      alert("올바른 숫자를 입력하세요 (start < end).");
      return;
    }
    const annotationId = crypto.randomUUID();
    editor
      .chain()
      .focus()
      .setArrow({
        arrowTargetStart: targetStart,
        arrowTargetEnd: targetEnd,
        colorIndex: selectedColorIndex,
        category: selectedCategory || null,
        annotationId,
      })
      .run();
  };

  const handleInlineNote = () => {
    if (!editor) return;
    const text = prompt("인라인 노트 텍스트를 입력하세요 (예: =foster, promote):");
    if (!text) return;
    const annotationId = crypto.randomUUID();
    editor
      .chain()
      .focus()
      .setInlineNote({
        text,
        colorIndex: selectedColorIndex,
        category: selectedCategory || null,
        annotationId,
      })
      .run();
  };

  // ---------------------------------------------------------------------------
  // 핸들러 — unset (선택 영역 mark 해제)
  // ---------------------------------------------------------------------------

  const handleUnsetTopLabel = () => editor?.chain().focus().unsetTopLabel().run();
  const handleUnsetBottomLabel = () => editor?.chain().focus().unsetBottomLabel().run();
  const handleUnsetBracket = () => editor?.chain().focus().unsetBracket().run();
  const handleUnsetArrow = () => editor?.chain().focus().unsetArrow().run();
  const handleUnsetInlineNote = () => editor?.chain().focus().unsetInlineNote().run();

  // ---------------------------------------------------------------------------
  // 핸들러 — 분석표 칩 x (annotationId 통째 삭제)
  // ---------------------------------------------------------------------------

  /**
   * handleRemoveAnnotation — 칩 x 동작.
   *
   * collectMarkRangesByAnnotationId 로 동일 annotationId 의 모든 range 를 수집한 뒤
   * 각 range 에 unsetMark 를 적용한다. 부분 unset 잔여 마크 버그 해결.
   */
  const handleRemoveAnnotation = useCallback(
    (annotationId: string) => {
      if (!editor) return;
      const ranges = collectMarkRangesByAnnotationId(editor.state.doc, annotationId);
      if (ranges.length === 0) return;

      let chain = editor.chain();
      for (const r of ranges) {
        chain = chain.setTextSelection({ from: r.from, to: r.to }).unsetMark(r.markName);
      }
      chain.run();
    },
    [editor]
  );

  // ---------------------------------------------------------------------------
  // 핸들러 — 직렬화 / 초기화
  // ---------------------------------------------------------------------------

  const handleSerialize = () => {
    if (!editor) return;
    const doc = editor.getJSON();
    const annotations = docToAnnotations(doc);
    setSerializedJson(JSON.stringify(annotations, null, 2));
  };

  const handleReset = () => {
    if (!editor) return;
    editor.commands.setContent(INITIAL_CONTENT);
    setSerializedJson(null);
  };

  const handleClearPanel = () => setSerializedJson(null);

  // ---------------------------------------------------------------------------
  // active 상태
  // ---------------------------------------------------------------------------

  const isHighlightActive = editor?.isActive("highlight") ?? false;
  const isUnderlineActive = editor?.isActive("underline") ?? false;
  const isTopLabelActive = editor?.isActive("topLabel") ?? false;
  const isBottomLabelActive = editor?.isActive("bottomLabel") ?? false;
  const isBracketActive = editor?.isActive("bracket") ?? false;
  const isArrowActive = editor?.isActive("arrow") ?? false;
  const isInlineNoteActive = editor?.isActive("inlineNote") ?? false;

  // ---------------------------------------------------------------------------
  // 렌더
  // ---------------------------------------------------------------------------

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* 헤더 */}
        <div className="flex items-center gap-4">
          <Link to="/" className="text-blue-600 hover:underline text-sm">
            ← 홈으로
          </Link>
          <h1 className="text-xl font-bold text-gray-900">구문분석 에디터 드래프트 (P1-2b)</h1>
          <span className="text-xs text-gray-400 bg-yellow-100 px-2 py-0.5 rounded">
            드래프트 — PM 검수용
          </span>
        </div>

        {/* 에디터 + 분석표 영역 */}
        <div className="flex flex-col gap-4">
          {/* 에디터 카드 */}
          <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
            {/* 툴바 그룹 1: annotation 적용 버튼 (7종) */}
            <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 space-y-2">
              <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                Annotation
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <AnnotationButton
                  label="형광펜"
                  active={isHighlightActive}
                  disabled={!editor}
                  onClick={handleHighlight}
                />
                <AnnotationButton
                  label="밑줄"
                  active={isUnderlineActive}
                  disabled={!editor}
                  onClick={handleUnderline}
                />
                <AnnotationButton
                  label="위 라벨"
                  active={isTopLabelActive}
                  disabled={!editor}
                  onClick={handleTopLabel}
                  onUnset={handleUnsetTopLabel}
                />
                <AnnotationButton
                  label="아래 라벨"
                  active={isBottomLabelActive}
                  disabled={!editor}
                  onClick={handleBottomLabel}
                  onUnset={handleUnsetBottomLabel}
                />
                <AnnotationButton
                  label="괄호"
                  active={isBracketActive}
                  disabled={!editor}
                  onClick={handleBracket}
                  onUnset={handleUnsetBracket}
                />
                <AnnotationButton
                  label="화살표"
                  active={isArrowActive}
                  disabled={!editor}
                  onClick={handleArrow}
                  onUnset={handleUnsetArrow}
                />
                <AnnotationButton
                  label="노트"
                  active={isInlineNoteActive}
                  disabled={!editor}
                  onClick={handleInlineNote}
                  onUnset={handleUnsetInlineNote}
                />
              </div>
            </div>

            {/* 툴바 그룹 2: color_index picker (12색 swatch) */}
            <div className="px-4 py-2 border-b border-gray-100 bg-gray-50 flex items-center gap-3">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide whitespace-nowrap">
                색상
              </span>
              <div className="flex flex-wrap gap-1">
                {COLOR_PALETTE.map((c) => (
                  <button
                    key={c.index}
                    type="button"
                    title={`색 ${c.index} (${c.label})`}
                    onClick={() => setSelectedColorIndex(c.index)}
                    className={[
                      "w-5 h-5 rounded-full border-2 transition-transform",
                      selectedColorIndex === c.index
                        ? "border-gray-700 scale-125"
                        : "border-transparent hover:scale-110",
                    ].join(" ")}
                    style={{ backgroundColor: c.hex }}
                  />
                ))}
              </div>
              <span className="text-xs text-gray-400">선택: #{selectedColorIndex}</span>
            </div>

            {/* 툴바 그룹 3: category select (5종) */}
            <div className="px-4 py-2 border-b border-gray-100 bg-gray-50 flex items-center gap-3">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide whitespace-nowrap">
                카테고리
              </span>
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="text-sm border border-gray-200 rounded-lg px-2 py-1 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-300"
              >
                {CATEGORY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* 툴바 제어: 직렬화 / 초기화 */}
            <div className="px-4 py-2 border-b border-gray-100 bg-gray-50 flex items-center gap-2">
              <button
                type="button"
                onClick={handleSerialize}
                disabled={!editor}
                className="px-3 py-1.5 text-sm font-medium rounded-lg bg-blue-50 border border-blue-200 text-blue-700 hover:bg-blue-100 transition-colors disabled:opacity-50"
              >
                SyntaxAnnotation[] 보기
              </button>
              <button
                type="button"
                onClick={handleReset}
                disabled={!editor}
                className="px-3 py-1.5 text-sm font-medium rounded-lg bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                초기화
              </button>
              {serializedJson && (
                <button
                  type="button"
                  onClick={handleClearPanel}
                  className="px-3 py-1.5 text-sm font-medium rounded-lg bg-white border border-gray-200 text-gray-400 hover:bg-gray-50 transition-colors"
                >
                  패널 닫기
                </button>
              )}
            </div>

            {/* Tiptap 에디터 본문 */}
            <EditorContent editor={editor} />
          </div>

          {/* 분석표 (본문 에디터 하단) */}
          <AnalysisTable chips={chips} onRemove={handleRemoveAnnotation} />
        </div>

        {/* 사용 안내 */}
        <p className="text-xs text-gray-400 leading-relaxed">
          텍스트를 선택 후 annotation 버튼을 클릭하세요. 라벨 / 노트 / 괄호 / 화살표는 prompt() 로
          텍스트 또는 좌표를 입력합니다 (드래프트 임시). 분석표 칩의 ✕ 버튼으로 annotation 을 통째
          삭제합니다. "SyntaxAnnotation[] 보기" 로 직렬화 결과를 확인하세요.
        </p>

        {/* SerializedAnnotation[] 직렬화 결과 패널 */}
        {serializedJson && (
          <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">
                SerializedAnnotation[] (SyntaxAnnotation 호환)
              </span>
              <span className="text-xs text-gray-400">
                kind / span / color_index / category / annotation_id 필드 확인
              </span>
            </div>
            <pre
              data-testid="serialized-annotations"
              className="p-4 text-xs text-gray-800 overflow-auto max-h-96 font-mono leading-relaxed"
            >
              {serializedJson}
            </pre>
          </div>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// 서브 컴포넌트
// ---------------------------------------------------------------------------

interface AnnotationButtonProps {
  label: string;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
  onUnset?: () => void;
}

function AnnotationButton({ label, active, disabled, onClick, onUnset }: AnnotationButtonProps) {
  return (
    <span className="inline-flex rounded-lg overflow-hidden border border-gray-200">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        className={[
          "px-2.5 py-1 text-sm font-medium transition-colors disabled:opacity-50",
          active ? "bg-blue-100 text-blue-800" : "bg-white text-gray-700 hover:bg-gray-50",
        ].join(" ")}
      >
        {label}
      </button>
      {onUnset && (
        <button
          type="button"
          onClick={onUnset}
          disabled={disabled}
          title={`${label} 해제`}
          className="px-1.5 py-1 text-xs text-gray-400 bg-white hover:bg-red-50 hover:text-red-500 border-l border-gray-200 transition-colors disabled:opacity-50"
        >
          ×
        </button>
      )}
    </span>
  );
}
