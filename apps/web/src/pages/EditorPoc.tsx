import { HighlightMark } from "@english-worksheet-tool/editor";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useState } from "react";
import { Link } from "react-router-dom";

/**
 * EditorPoc — Tiptap 구문분석 에디터 PoC (Sprint 0 #7)
 *
 * 검증 포인트:
 * 1. 텍스트 선택 후 "하이라이트 토글" 버튼 → highlight mark 적용/해제
 * 2. "JSON 보기" 버튼 → ProseMirror 문서 JSON 직렬화 + 화면 출력
 * 3. JSON 안에 highlight mark가 있어야 함
 *
 * architect에게 전달 메모 (직렬화 관찰):
 *   ProseMirror JSON에서 mark range는 character offset이 아닌
 *   doc > content[] 트리 구조로 표현된다. 하이라이트가 걸린 구간은
 *   별도 text 노드로 분리되며, 해당 노드의 marks 배열에
 *   { type: "highlight", attrs: { color: "#..." } } 형태로 기록된다.
 *   즉, 직렬화된 JSON만으로는 원본 텍스트에서의 절대 character offset을
 *   즉시 알 수 없고, 트리를 순회하며 앞선 텍스트 노드 길이를 누적해야
 *   fromPos / toPos 를 복원할 수 있다. SyntaxAnnotation 변환 시
 *   이 누적 순회 로직이 필요하다.
 */

// Tiptap 에디터에 사용할 extension 목록
const EXTENSIONS = [
  StarterKit,
  HighlightMark, // multicolor: true 설정됨
];

// PoC 초기 콘텐츠 — 구문분석 예시 문장
const INITIAL_CONTENT =
  "<p>The student who studied hard passed the exam.</p><p>Scientists have discovered that regular exercise significantly improves cognitive function.</p>";

export function EditorPoc() {
  // JSON 직렬화 결과를 화면에 출력하기 위한 상태
  const [serializedJson, setSerializedJson] = useState<string | null>(null);

  const editor = useEditor({
    extensions: EXTENSIONS,
    content: INITIAL_CONTENT,
    editorProps: {
      attributes: {
        // 에디터 영역 스타일 — Tailwind prose 클래스
        class: "min-h-[120px] p-4 focus:outline-none prose prose-sm max-w-none",
      },
    },
  });

  // 선택된 텍스트에 하이라이트 토글
  const handleHighlightToggle = () => {
    if (!editor) return;
    editor.chain().focus().toggleHighlight({ color: "#fef08a" }).run();
  };

  // 현재 에디터 상태를 ProseMirror JSON으로 직렬화
  const handleSerialize = () => {
    if (!editor) return;
    const json = editor.getJSON();
    setSerializedJson(JSON.stringify(json, null, 2));
  };

  // JSON 패널 초기화
  const handleClear = () => {
    setSerializedJson(null);
  };

  // 하이라이트 적용 여부 (버튼 활성 상태 표시용)
  const isHighlightActive = editor?.isActive("highlight") ?? false;

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* 헤더 */}
        <div className="flex items-center gap-4">
          <Link to="/" className="text-blue-600 hover:underline text-sm">
            ← 홈으로
          </Link>
          <h1 className="text-xl font-bold text-gray-900">Tiptap 구문분석 에디터 PoC</h1>
        </div>

        {/* 에디터 영역 */}
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
          {/* 툴바 */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-gray-50">
            <button
              type="button"
              onClick={handleHighlightToggle}
              disabled={!editor}
              className={[
                "px-3 py-1.5 text-sm font-medium rounded-lg transition-colors",
                isHighlightActive
                  ? "bg-yellow-300 text-yellow-900 ring-2 ring-yellow-400"
                  : "bg-white border border-gray-200 text-gray-700 hover:bg-yellow-50",
              ].join(" ")}
            >
              하이라이트 토글
            </button>
            <button
              type="button"
              onClick={handleSerialize}
              disabled={!editor}
              className="px-3 py-1.5 text-sm font-medium rounded-lg bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
            >
              JSON 보기
            </button>
            {serializedJson && (
              <button
                type="button"
                onClick={handleClear}
                className="px-3 py-1.5 text-sm font-medium rounded-lg bg-white border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors"
              >
                JSON 닫기
              </button>
            )}
          </div>

          {/* Tiptap 에디터 본문 */}
          <EditorContent editor={editor} />
        </div>

        {/* 사용 안내 */}
        <p className="text-xs text-gray-400">
          텍스트를 선택한 뒤 "하이라이트 토글"을 클릭하면 노란 형광펜이 적용됩니다. "JSON 보기"로
          ProseMirror 문서 JSON을 확인하세요.
        </p>

        {/* JSON 직렬화 결과 패널 */}
        {serializedJson && (
          <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">ProseMirror 문서 JSON</span>
              <span className="text-xs text-gray-400">
                mark range는 텍스트 노드 분리 방식으로 표현됨
              </span>
            </div>
            <pre
              data-testid="serialized-json"
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
