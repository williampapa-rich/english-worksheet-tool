import {
  ArrowMark,
  BottomLabelMark,
  BracketMark,
  HighlightMark,
  InlineNoteMark,
  TopLabelMark,
  UnderlineMark,
  WordSnapExtension,
  docToAnnotations,
} from "@english-worksheet-tool/editor";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useState } from "react";
import { Link } from "react-router-dom";
import "./EditorPoc.css";

/**
 * EditorPoc — P1-2a-draft 구문분석 에디터 드래프트
 *
 * 목표: PM(Dennis) 이 외부에서 복귀했을 때 브라우저에서 7종 annotation 을 모두
 * 찍어보고 시각·직렬화 결과를 검수할 수 있는 드래프트 에디터.
 *
 * 툴바 3그룹:
 *   1. annotation 적용 그룹 (7버튼)
 *   2. 12색 color_index picker
 *   3. 5종 category select
 *
 * 비DoD (이번 PR 에서 하지 않음):
 *   - 컨텍스트 메뉴 (우클릭)
 *   - API 통합 / HWPX 다운로드
 *   - ArrowMark Decoration API 전환
 *   - 다중 단락 직렬화 검증
 *
 * TODO: PM 결정 필요 항목은 plan §"미결정 / PM 인터뷰 대상" 참조.
 */

// ---------------------------------------------------------------------------
// 상수
// ---------------------------------------------------------------------------

/**
 * 7종 extension 등록.
 * UnderlineMark = @tiptap/extension-underline 래퍼.
 * HighlightMark = @tiptap/extension-highlight (multicolor: true).
 */
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

/**
 * Fixture 문장 — 7종 annotation 을 모두 적용 가능한 충분히 긴 영어 문장.
 * 레퍼런스 영상에서 자주 등장하는 구문 분석 패턴을 포함.
 */
const INITIAL_CONTENT =
  "<p>The student who had studied hard for the exam passed with an excellent score, which made her parents extremely proud.</p><p>Scientists have discovered that regular exercise significantly improves cognitive function and helps prevent age-related memory decline.</p>";

/**
 * TODO: PM 결정 — color palette §3.3
 * 현재 Tailwind palette 에서 임의 12개 선택. 레퍼런스 영상 §3.3 분석 후 교체 예정.
 * color_index 별 의미 (sentence_role 매핑 등) 도 미결정.
 */
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
// 컴포넌트
// ---------------------------------------------------------------------------

export function EditorPoc() {
  // 다음 annotation 에 적용될 color_index (0 = 미설정)
  const [selectedColorIndex, setSelectedColorIndex] = useState<number>(1);
  // 다음 annotation 에 적용될 category
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  // SerializedAnnotation[] 직렬화 결과 패널
  const [serializedJson, setSerializedJson] = useState<string | null>(null);

  const editor = useEditor({
    extensions: EXTENSIONS,
    content: INITIAL_CONTENT,
    editorProps: {
      attributes: {
        class: "min-h-[160px] p-4 focus:outline-none prose prose-sm max-w-none",
      },
    },
  });

  // ---------------------------------------------------------------------------
  // 핸들러 — annotation 적용
  // ---------------------------------------------------------------------------

  /** highlight: color 는 selectedColorIndex 에서 팔레트 hex 로 변환 */
  const handleHighlight = () => {
    if (!editor) return;
    const palette = COLOR_PALETTE.find((c) => c.index === selectedColorIndex);
    const color = palette?.hex ?? "#fef08a";
    editor.chain().focus().toggleHighlight({ color }).run();
  };

  /** underline: @tiptap/extension-underline toggleUnderline 사용 */
  const handleUnderline = () => {
    if (!editor) return;
    editor.chain().focus().toggleUnderline().run();
  };

  /** top_label: 라벨 텍스트를 prompt() 로 받아 setTopLabel */
  const handleTopLabel = () => {
    if (!editor) return;
    const text = prompt("상단 라벨 텍스트를 입력하세요 (예: S, V, 관계절):");
    if (!text) return;
    editor
      .chain()
      .focus()
      .setTopLabel({
        text,
        colorIndex: selectedColorIndex,
        category: selectedCategory || null,
      })
      .run();
  };

  /** bottom_label: 라벨 텍스트를 prompt() 로 받아 setBottomLabel */
  const handleBottomLabel = () => {
    if (!editor) return;
    const text = prompt("하단 라벨 텍스트를 입력하세요 (예: S, V, O):");
    if (!text) return;
    editor
      .chain()
      .focus()
      .setBottomLabel({
        text,
        colorIndex: selectedColorIndex,
        category: selectedCategory || null,
      })
      .run();
  };

  /**
   * bracket: bracketStyle 을 선택 후 setBracket
   * TODO: PM 결정 — bracket 의 style 표현 (() / {} / []) 방식
   */
  const handleBracket = () => {
    if (!editor) return;
    const style = prompt("괄호 스타일 선택: () / {} / []", "()");
    if (!style || !["()", "{}", "[]"].includes(style)) return;
    editor
      .chain()
      .focus()
      .setBracket({
        bracketStyle: style as "()" | "{}" | "[]",
        colorIndex: selectedColorIndex,
        category: selectedCategory || null,
      })
      .run();
  };

  /**
   * arrow: 도착점 char offset 을 prompt() 로 받아 setArrow
   * 실제 SVG 화살표는 P1-8c 영역. 드래프트는 점선 underline.
   */
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
    editor
      .chain()
      .focus()
      .setArrow({
        arrowTargetStart: targetStart,
        arrowTargetEnd: targetEnd,
        colorIndex: selectedColorIndex,
        category: selectedCategory || null,
      })
      .run();
  };

  /**
   * inline_note: 노트 텍스트를 prompt() 로 받아 setInlineNote
   * TODO: PM 결정 — inline_note 위치 / 분리 단락 여부 (P1-7 §6 #2 미결정)
   */
  const handleInlineNote = () => {
    if (!editor) return;
    const text = prompt("인라인 노트 텍스트를 입력하세요 (예: =foster, promote):");
    if (!text) return;
    editor
      .chain()
      .focus()
      .setInlineNote({
        text,
        colorIndex: selectedColorIndex,
        category: selectedCategory || null,
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
  // 핸들러 — 직렬화 / 초기화
  // ---------------------------------------------------------------------------

  /** docToAnnotations 로 SerializedAnnotation[] 직렬화 후 패널 표시 */
  const handleSerialize = () => {
    if (!editor) return;
    const doc = editor.getJSON();
    const annotations = docToAnnotations(doc);
    setSerializedJson(JSON.stringify(annotations, null, 2));
  };

  /** fixture 문장으로 doc 리셋 */
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
          <h1 className="text-xl font-bold text-gray-900">구문분석 에디터 드래프트 (P1-2a)</h1>
          <span className="text-xs text-gray-400 bg-yellow-100 px-2 py-0.5 rounded">
            드래프트 — PM 검수용
          </span>
        </div>

        {/* 에디터 영역 */}
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
          {/* ---------------------------------------------------------------
           * 툴바 그룹 1: annotation 적용 버튼 (7종)
           * --------------------------------------------------------------- */}
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 space-y-2">
            <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
              Annotation
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {/* highlight */}
              <AnnotationButton
                label="형광펜"
                active={isHighlightActive}
                disabled={!editor}
                onClick={handleHighlight}
              />
              {/* underline */}
              <AnnotationButton
                label="밑줄"
                active={isUnderlineActive}
                disabled={!editor}
                onClick={handleUnderline}
              />
              {/* top_label */}
              <AnnotationButton
                label="위 라벨"
                active={isTopLabelActive}
                disabled={!editor}
                onClick={handleTopLabel}
                onUnset={handleUnsetTopLabel}
              />
              {/* bottom_label */}
              <AnnotationButton
                label="아래 라벨"
                active={isBottomLabelActive}
                disabled={!editor}
                onClick={handleBottomLabel}
                onUnset={handleUnsetBottomLabel}
              />
              {/* bracket */}
              <AnnotationButton
                label="괄호"
                active={isBracketActive}
                disabled={!editor}
                onClick={handleBracket}
                onUnset={handleUnsetBracket}
              />
              {/* arrow */}
              <AnnotationButton
                label="화살표"
                active={isArrowActive}
                disabled={!editor}
                onClick={handleArrow}
                onUnset={handleUnsetArrow}
              />
              {/* inline_note */}
              <AnnotationButton
                label="노트"
                active={isInlineNoteActive}
                disabled={!editor}
                onClick={handleInlineNote}
                onUnset={handleUnsetInlineNote}
              />
            </div>
          </div>

          {/* ---------------------------------------------------------------
           * 툴바 그룹 2: color_index picker (12색 swatch)
           * ---------------------------------------------------------------
           * TODO: PM 결정 — color_index 별 의미 (sentence_role 매핑 등) 미정.
           * 드래프트는 순수 색 팔레트.
           * --------------------------------------------------------------- */}
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

          {/* ---------------------------------------------------------------
           * 툴바 그룹 3: category select (5종)
           * --------------------------------------------------------------- */}
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

          {/* ---------------------------------------------------------------
           * 툴바 제어: 직렬화 / 초기화
           * --------------------------------------------------------------- */}
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

        {/* 사용 안내 */}
        <p className="text-xs text-gray-400 leading-relaxed">
          텍스트를 선택 후 annotation 버튼을 클릭하세요. 라벨 / 노트 / 괄호 / 화살표는 prompt() 로
          텍스트 또는 좌표를 입력합니다 (드래프트 임시). "SyntaxAnnotation[] 보기" 로 직렬화 결과를
          확인하고, "초기화" 로 fixture 문장으로 되돌립니다.
        </p>

        {/* SerializedAnnotation[] 직렬화 결과 패널 */}
        {serializedJson && (
          <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">
                SerializedAnnotation[] (SyntaxAnnotation 호환)
              </span>
              <span className="text-xs text-gray-400">
                kind / span / color_index / category 필드 확인
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

/**
 * AnnotationButton — annotation 적용/해제 버튼.
 * active 상태일 때 색 강조. onUnset 이 있으면 "×" 해제 버튼 추가.
 */
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
