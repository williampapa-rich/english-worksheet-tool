import type { ReactElement } from "react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  type CompatibleTypeInfo,
  type ExtractedPassageResult,
  type Question,
  createCrossTypeVariant,
  extractPassageImage,
  extractPassagePdf,
  extractPassageText,
  getCompatibleTypes,
} from "../lib/api";

// ---------------------------------------------------------------------------
// (V1~V10 type-preserving 변형 테이블 — 폐기 예정, cross-type 로 전환)
// ---------------------------------------------------------------------------

// Question type 한국어 표시명
const QUESTION_TYPE_LABELS: Record<string, string> = {
  purpose_18: "목적(18)",
  mood_19: "심경(19)",
  assertion_20: "주장(20)",
  underline_implication_21: "밑줄함의(21)",
  gist_22: "요지(22)",
  theme_23: "주제(23)",
  title_24: "제목(24)",
  chart_25: "도표(25)",
  figure_match_26: "인물일치(26)",
  notice_27: "안내문(27)",
  notice_28: "안내문(28)",
  grammar_29: "어법(29)",
  vocabulary_30: "어휘(30)",
  blank_phrase_31: "빈칸-구(31)",
  blank_clause_32: "빈칸-절(32)",
  blank_clause_33: "빈칸-절(33)",
  blank_clause_34: "빈칸-절(34)",
  irrelevant_sentence_35: "무관문장(35)",
  order_36: "순서배열(36)",
  order_37: "순서배열(37)",
  insertion_38: "문장삽입(38)",
  insertion_39: "문장삽입(39)",
  summary_40: "요약문(40)",
  long_set_41_42: "장문(41-42)",
  long_set_43_45: "장문독해(43-45)",
};

const TARGET_GRADE_OPTIONS = [
  { value: "middle_1", label: "중1" },
  { value: "middle_2", label: "중2" },
  { value: "middle_3", label: "중3" },
  { value: "high_1", label: "고1" },
  { value: "high_2", label: "고2" },
  { value: "high_3", label: "고3 (default)" },
  { value: "csat", label: "수능" },
];

type InputTab = "text" | "image" | "pdf";

// ---------------------------------------------------------------------------
// 서브 컴포넌트 — QuestionCard (cross-type variant)
// ---------------------------------------------------------------------------

interface QuestionCardProps {
  question: Question;
  crossTypeResults: Question[];
  onCrossTypeCreate: (questionId: string, targetType: string) => void;
  crossTypeLoading: boolean;
  crossTypeError: string | null;
}

function QuestionCard({
  question,
  crossTypeResults,
  onCrossTypeCreate,
  crossTypeLoading,
  crossTypeError,
}: QuestionCardProps): ReactElement {
  const [compatibleTypes, setCompatibleTypes] = useState<CompatibleTypeInfo[]>([]);
  const [typesLoaded, setTypesLoaded] = useState(false);
  const [selectedType, setSelectedType] = useState("");
  const [showSelector, setShowSelector] = useState(false);

  const typeLabel = QUESTION_TYPE_LABELS[question.type] ?? question.type;

  async function loadCompatibleTypes(): Promise<void> {
    if (typesLoaded) {
      setShowSelector(true);
      return;
    }
    try {
      const types = await getCompatibleTypes(question.id);
      setCompatibleTypes(types);
      setTypesLoaded(true);
      setShowSelector(true);
      if (types.length > 0 && types[0] != null) setSelectedType(types[0].type);
    } catch (err) {
      console.error("Failed to load compatible types:", err);
    }
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
      {/* 헤더 */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="inline-block bg-blue-50 text-blue-700 text-xs font-medium px-2 py-0.5 rounded-md">
            {typeLabel}
          </span>
          {question.number != null && (
            <span className="ml-2 text-xs text-gray-400">#{question.number}</span>
          )}
        </div>
        <span className="text-xs text-gray-400 font-mono">{question.id.slice(0, 8)}…</span>
      </div>

      {/* 지시문 */}
      {question.question_text && (
        <p className="text-sm text-gray-700 leading-relaxed">{question.question_text}</p>
      )}

      {/* 선택지 */}
      {question.choices.length > 0 && (
        <ol className="space-y-1">
          {question.choices.map((choice, idx) => (
            <li
              key={`${question.id}-choice-${idx}`}
              className={`text-sm px-3 py-1.5 rounded-lg ${
                idx + 1 === question.answer
                  ? "bg-green-50 text-green-800 font-medium border border-green-200"
                  : "text-gray-600"
              }`}
            >
              <span className="font-medium mr-1.5">{"①②③④⑤"[idx]}</span>
              {choice}
            </li>
          ))}
        </ol>
      )}

      {/* qa-validator 상태 */}
      <div className="flex items-center gap-2 text-xs">
        <span
          className={`inline-block w-2 h-2 rounded-full ${
            question.uniqueness_validated ? "bg-green-400" : "bg-gray-300"
          }`}
        />
        <span className="text-gray-500">
          {question.uniqueness_validated ? "유일성 검증 통과" : "검증 미완료"}
        </span>
        {question.uniqueness_validator_note && (
          <span className="text-gray-400 truncate max-w-xs">
            — {question.uniqueness_validator_note}
          </span>
        )}
      </div>

      {/* 유형 변경 */}
      <div className="pt-2 border-t border-gray-100">
        <p className="text-xs font-medium text-gray-500 mb-2">유형 변경</p>

        {!showSelector && (
          <button
            type="button"
            onClick={() => {
              void loadCompatibleTypes();
            }}
            className="text-xs bg-indigo-50 border border-indigo-200 text-indigo-700 px-3 py-1.5 rounded-lg hover:bg-indigo-100 transition-colors"
          >
            변환 가능한 유형 보기
          </button>
        )}

        {showSelector && compatibleTypes.length > 0 && (
          <div className="flex items-center gap-2">
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              disabled={crossTypeLoading}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:border-indigo-400"
            >
              {compatibleTypes.map((ct) => (
                <option key={ct.type} value={ct.type}>
                  {ct.label} {ct.level === "conditional" ? " ⚠️" : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={crossTypeLoading || !selectedType}
              onClick={() => onCrossTypeCreate(question.id, selectedType)}
              className="text-xs bg-indigo-600 text-white px-4 py-1.5 rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {crossTypeLoading ? "생성 중…" : "변형 생성"}
            </button>
          </div>
        )}

        {showSelector && compatibleTypes.length === 0 && (
          <p className="text-xs text-gray-400">변환 가능한 유형이 없습니다.</p>
        )}

        {crossTypeError && <p className="text-xs text-red-600 mt-1">{crossTypeError}</p>}
      </div>

      {/* 변형 결과 */}
      {crossTypeResults.map((result) => (
        <CrossTypeResultCard key={result.id} result={result} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 서브 컴포넌트 — CrossTypeResultCard
// ---------------------------------------------------------------------------

// 어법/어휘 본문의 ①_word_ 마커를 밑줄 스타일로 렌더링
function renderMarkedPassage(text: string): ReactElement {
  const parts = text.split(/([①②③④⑤]_[^_]+_)/g);
  return (
    <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
      {parts.map((part) => {
        const match = part.match(/^([①②③④⑤])_([^_]+)_$/);
        if (match) {
          return (
            <span key={`marker-${match[1]}-${match[2]}`}>
              {match[1]}
              <span className="underline decoration-2 font-medium">{match[2]}</span>
            </span>
          );
        }
        return <span key={part}>{part}</span>;
      })}
    </p>
  );
}

// 보기가 본문 내 마커와 동일한 유형 (어법/어휘/무관문장/문장삽입)
const MARKER_CHOICE_TYPES = new Set([
  "grammar_29",
  "vocabulary_30",
  "irrelevant_sentence_35",
  "insertion_38",
  "insertion_39",
]);

function CrossTypeResultCard({ result }: { result: Question }): ReactElement {
  const typeLabel = QUESTION_TYPE_LABELS[result.type] ?? result.type;
  const modifiedPassage = result.variant_metadata?.modified_passage as string | undefined;
  const reconstructedPassage = result.variant_metadata?.reconstructed_passage_text as
    | string
    | undefined;
  const displayPassage = modifiedPassage ?? reconstructedPassage;
  const isMarkerType = MARKER_CHOICE_TYPES.has(result.type);
  const isGrammarVocab = result.type === "grammar_29" || result.type === "vocabulary_30";

  return (
    <div className="mt-3 bg-indigo-50 border border-indigo-200 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="inline-block bg-indigo-100 text-indigo-700 text-xs font-medium px-2 py-0.5 rounded-md">
            {typeLabel}
          </span>
          <span className="text-xs text-indigo-500 font-medium">유형 변경</span>
        </div>
        <span className="text-xs text-gray-400 font-mono">{result.id.slice(0, 8)}…</span>
      </div>

      {/* 본문 (변형 또는 복원) */}
      {displayPassage && (
        <div className="bg-white border border-indigo-100 rounded-lg p-3">
          <p className="text-xs font-medium text-indigo-600 mb-1.5">
            {modifiedPassage ? "변형 본문" : "복원 본문"}
          </p>
          {isGrammarVocab ? (
            renderMarkedPassage(displayPassage)
          ) : (
            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
              {displayPassage}
            </p>
          )}
        </div>
      )}

      {result.question_text && (
        <p className="text-sm text-gray-700 leading-relaxed">{result.question_text}</p>
      )}

      {/* 보기 — 마커형(어법/어휘/무관/삽입)은 이미 본문에 번호 있으므로 별도 표시 생략 가능 */}
      {result.choices.length > 0 && !isMarkerType && (
        <ol className="space-y-1">
          {result.choices.map((choice, idx) => (
            <li
              key={`${result.id}-choice-${idx}`}
              className={`text-sm px-3 py-1.5 rounded-lg ${
                idx + 1 === result.answer
                  ? "bg-green-100 text-green-800 font-medium border border-green-300"
                  : "text-gray-600"
              }`}
            >
              <span className="font-medium mr-1.5">{"①②③④⑤"[idx]}</span>
              {choice}
            </li>
          ))}
        </ol>
      )}

      {/* 마커형은 정답만 표시 */}
      {isMarkerType && (
        <p className="text-sm font-medium text-green-700">정답: {"①②③④⑤"[result.answer - 1]}</p>
      )}

      {result.explanation && (
        <p className="text-xs text-gray-500 leading-relaxed">
          <span className="font-medium">해설:</span> {result.explanation}
        </p>
      )}

      <div className="flex items-center gap-2 text-xs pt-1 border-t border-indigo-200">
        <span
          className={`inline-block w-2 h-2 rounded-full ${
            result.uniqueness_validated ? "bg-green-400" : "bg-gray-300"
          }`}
        />
        <span className="text-gray-600">
          {result.uniqueness_validated ? "유일성 검증 통과" : "검증 미완료"}
        </span>
        {result.uniqueness_validator_note && (
          <span className="text-gray-500">— {result.uniqueness_validator_note}</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 메인 페이지
// ---------------------------------------------------------------------------

/**
 * PassageNewPage — 신규 지문/문제 입력 페이지 (Phase 3 운영 검수 진입점).
 *
 * 3탭 입력 (텍스트 / 이미지 / PDF) → POST /passages/extract → 추출 결과 표시
 * → Question 별 변형 버튼 (catalog v0.4 §3.2.0 QuestionType 자동 필터)
 * → POST /questions/{id}/variants/{kind} → 변형 결과 표시.
 */
export function PassageNewPage(): ReactElement {
  // ─── 입력 상태 ────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<InputTab>("text");
  const [textBody, setTextBody] = useState("");
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [targetGrade, setTargetGrade] = useState("high_3");
  const imageInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);

  // ─── 추출 상태 ────────────────────────────────────────────────────────
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [extractResults, setExtractResults] = useState<ExtractedPassageResult[] | null>(null);

  // ─── Cross-type 변형 상태 ────────────────────────────────────────────
  // key: questionId
  const [crossTypeLoading, setCrossTypeLoading] = useState<Record<string, boolean>>({});
  const [crossTypeErrors, setCrossTypeErrors] = useState<Record<string, string | null>>({});
  const [crossTypeResults, setCrossTypeResults] = useState<Record<string, Question[]>>({});

  // ─── 추출 핸들러 ──────────────────────────────────────────────────────

  async function handleExtract(): Promise<void> {
    setExtractError(null);
    setExtractResults(null);

    // 입력 검증
    if (activeTab === "text" && !textBody.trim()) {
      setExtractError("지문 텍스트를 입력해주세요.");
      return;
    }
    if (activeTab === "image" && imageFiles.length === 0) {
      setExtractError("이미지 파일을 선택해주세요.");
      return;
    }
    if (activeTab === "pdf" && !pdfFile) {
      setExtractError("PDF 파일을 선택해주세요.");
      return;
    }

    setExtracting(true);
    try {
      let results: ExtractedPassageResult[];
      if (activeTab === "text") {
        results = await extractPassageText(textBody, targetGrade);
      } else if (activeTab === "image") {
        results = await extractPassageImage(imageFiles, targetGrade);
      } else {
        // pdfFile != null は activeTab === "pdf" 分岐に入る前に検証済み
        results = await extractPassagePdf(pdfFile as File, targetGrade);
      }
      setExtractResults(results);
    } catch (err) {
      setExtractError(err instanceof Error ? err.message : String(err));
    } finally {
      setExtracting(false);
    }
  }

  // ─── Cross-type 변형 생성 핸들러 ──────────────────────────────────────

  async function handleCrossTypeCreate(questionId: string, targetType: string): Promise<void> {
    setCrossTypeLoading((prev) => ({ ...prev, [questionId]: true }));
    setCrossTypeErrors((prev) => ({ ...prev, [questionId]: null }));

    try {
      const result = await createCrossTypeVariant(questionId, targetType);
      setCrossTypeResults((prev) => ({
        ...prev,
        [questionId]: [...(prev[questionId] ?? []), result],
      }));
    } catch (err) {
      setCrossTypeErrors((prev) => ({
        ...prev,
        [questionId]: err instanceof Error ? err.message : String(err),
      }));
    } finally {
      setCrossTypeLoading((prev) => ({ ...prev, [questionId]: false }));
    }
  }

  // ─── 렌더 ─────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">새 지문 / 문제 입력</h1>
            <p className="text-sm text-gray-500 mt-1">Phase 3 — 변형문제 생성 진입점</p>
          </div>
          <Link to="/" className="text-sm text-gray-500 hover:text-gray-700 transition-colors">
            ← 홈
          </Link>
        </div>

        {/* 에러 */}
        {extractError && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4">
            <p className="font-medium">추출 실패</p>
            <p className="text-sm mt-1">{extractError}</p>
          </div>
        )}

        {/* 입력 영역 */}
        <div className="bg-white border border-gray-200 rounded-2xl p-6 space-y-5">
          {/* 탭 */}
          <div className="flex border-b border-gray-200">
            {(["text", "image", "pdf"] as InputTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                }`}
              >
                {tab === "text" ? "텍스트" : tab === "image" ? "이미지" : "PDF"}
              </button>
            ))}
          </div>

          {/* 탭 콘텐츠 */}
          {activeTab === "text" && (
            <div>
              <label htmlFor="pn-body" className="block text-sm font-medium text-gray-700 mb-1.5">
                영어 지문 + 문제 (선택)
              </label>
              <textarea
                id="pn-body"
                value={textBody}
                onChange={(e) => setTextBody(e.target.value)}
                rows={12}
                placeholder="영어 지문을 붙여넣으세요. 5지선다 문제와 정답이 포함된 경우 함께 추출됩니다."
                className="w-full bg-white border border-gray-200 rounded-xl px-4 py-3 font-mono text-sm focus:outline-none focus:border-blue-400 resize-y"
              />
            </div>
          )}

          {activeTab === "image" && (
            <div>
              {/* label wraps input — accessible dropzone, no role="button" needed */}
              <label htmlFor="pn-image-input" className="block cursor-pointer">
                <span className="block text-sm font-medium text-gray-700 mb-1.5">
                  이미지 파일 (PNG / JPG) — 다중 선택 가능
                </span>
                <div className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center hover:border-blue-400 transition-colors">
                  <input
                    id="pn-image-input"
                    ref={imageInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/jpg"
                    multiple
                    className="hidden"
                    onChange={(e) => {
                      const files = Array.from(e.target.files ?? []);
                      setImageFiles(files);
                    }}
                  />
                  {imageFiles.length === 0 ? (
                    <>
                      <p className="text-sm text-gray-500">클릭하거나 파일을 여기에 드래그하세요</p>
                      <p className="text-xs text-gray-400 mt-1">
                        PNG, JPG — 여러 페이지는 파일 여러 개
                      </p>
                    </>
                  ) : (
                    <ul className="text-sm text-gray-700 text-left space-y-1">
                      {imageFiles.map((f) => (
                        <li key={f.name} className="flex items-center gap-2">
                          <span className="text-green-500">✓</span>
                          {f.name}
                          <span className="text-xs text-gray-400">
                            ({(f.size / 1024).toFixed(0)} KB)
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </label>
              {imageFiles.length > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    setImageFiles([]);
                    if (imageInputRef.current) imageInputRef.current.value = "";
                  }}
                  className="text-xs text-gray-400 hover:text-red-500 mt-2 transition-colors"
                >
                  파일 초기화
                </button>
              )}
            </div>
          )}

          {activeTab === "pdf" && (
            <div>
              {/* label wraps input — accessible dropzone */}
              <label htmlFor="pn-pdf-input" className="block cursor-pointer">
                <span className="block text-sm font-medium text-gray-700 mb-1.5">
                  PDF 파일 (1건)
                </span>
                <div className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center hover:border-blue-400 transition-colors">
                  <input
                    id="pn-pdf-input"
                    ref={pdfInputRef}
                    type="file"
                    accept="application/pdf"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0] ?? null;
                      setPdfFile(file);
                    }}
                  />
                  {!pdfFile ? (
                    <>
                      <p className="text-sm text-gray-500">클릭하거나 PDF를 여기에 드래그하세요</p>
                      <p className="text-xs text-gray-400 mt-1">
                        텍스트 레이어 PDF 는 빠른 추출, 스캔본은 Vision LLM 사용
                      </p>
                    </>
                  ) : (
                    <div className="flex items-center gap-2 justify-center">
                      <span className="text-green-500">✓</span>
                      <span className="text-sm text-gray-700">{pdfFile.name}</span>
                      <span className="text-xs text-gray-400">
                        ({(pdfFile.size / 1024).toFixed(0)} KB)
                      </span>
                    </div>
                  )}
                </div>
              </label>
              {pdfFile && (
                <button
                  type="button"
                  onClick={() => {
                    setPdfFile(null);
                    if (pdfInputRef.current) pdfInputRef.current.value = "";
                  }}
                  className="text-xs text-gray-400 hover:text-red-500 mt-2 transition-colors"
                >
                  파일 초기화
                </button>
              )}
            </div>
          )}

          {/* 대상 학년 */}
          <div className="flex items-center gap-4">
            <label
              htmlFor="pn-grade"
              className="text-sm font-medium text-gray-700 whitespace-nowrap"
            >
              대상 학년 <span className="text-gray-400 font-normal">(선택)</span>
            </label>
            <select
              id="pn-grade"
              value={targetGrade}
              onChange={(e) => setTargetGrade(e.target.value)}
              className="bg-white border border-gray-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-blue-400"
            >
              {TARGET_GRADE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* 추출 버튼 */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={extracting}
              onClick={handleExtract}
              className="bg-blue-600 text-white font-medium px-6 py-2.5 rounded-xl hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {extracting ? "추출 중… (LLM 처리 중)" : "추출하기"}
            </button>
            {extracting && (
              <p className="text-xs text-gray-400">Vision LLM 호출 시 30~60초 소요될 수 있습니다</p>
            )}
          </div>
        </div>

        {/* 추출 결과 */}
        {extractResults && (
          <div className="space-y-5">
            <h2 className="text-lg font-semibold text-gray-800">
              추출 결과 — {extractResults.length}건
            </h2>

            {extractResults.map((result, resultIdx) => (
              <div
                key={result.passage.id}
                className="bg-white border border-gray-200 rounded-2xl overflow-hidden"
              >
                {/* 지문 헤더 */}
                <div className="bg-gray-50 border-b border-gray-200 px-6 py-4 flex items-center justify-between gap-4">
                  <div>
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                      지문 {resultIdx + 1}
                    </span>
                    {result.passage.title && (
                      <p className="text-sm font-medium text-gray-800 mt-0.5">
                        {result.passage.title}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-gray-400">
                      ID: {result.passage.id.slice(0, 8)}…
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        void navigator.clipboard.writeText(result.passage.id);
                      }}
                      className="text-xs text-gray-400 hover:text-blue-600 transition-colors border border-gray-200 px-2 py-0.5 rounded-md"
                    >
                      복사
                    </button>
                  </div>
                </div>

                <div className="p-6 space-y-5">
                  {/* 본문 */}
                  <div>
                    <p className="text-xs font-medium text-gray-500 mb-2">
                      본문 ({result.passage.paragraphs?.length ?? 1}단락)
                    </p>
                    <p className="text-sm text-gray-800 leading-relaxed bg-gray-50 rounded-xl p-4 whitespace-pre-wrap">
                      {result.passage.body_text}
                    </p>
                    <div className="mt-2 flex gap-4 text-xs text-gray-400">
                      <Link
                        to={`/editor/${result.passage.id}`}
                        className="text-blue-500 hover:text-blue-700 transition-colors"
                      >
                        구문분석 에디터에서 열기 →
                      </Link>
                    </div>
                  </div>

                  {/* Translation */}
                  {result.translation && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-2">한글 해석</p>
                      <p className="text-sm text-gray-700 leading-relaxed bg-yellow-50 rounded-xl p-4">
                        {result.translation.text}
                      </p>
                    </div>
                  )}

                  {/* Vocabulary */}
                  {result.vocabulary.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-2">
                        어휘 ({result.vocabulary.length}개)
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {result.vocabulary.map((v) => (
                          <span
                            key={v.id}
                            className="inline-flex items-center gap-1 bg-blue-50 border border-blue-100 text-blue-800 text-xs px-2.5 py-1 rounded-full"
                          >
                            <span className="font-medium">{v.word}</span>
                            {v.pos && <span className="text-blue-400">{v.pos}</span>}
                            <span className="text-blue-600">{v.meaning_ko}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Questions */}
                  <div>
                    <p className="text-xs font-medium text-gray-500 mb-3">
                      추출된 문제{" "}
                      {result.questions.length > 0 ? `(${result.questions.length}개)` : "— 없음"}
                    </p>

                    {result.questions.length === 0 ? (
                      <div className="bg-gray-50 rounded-xl p-4 text-sm text-gray-500 text-center">
                        지문만 추출됨. 변형 생성하려면 문제가 필요합니다.
                        <br />
                        <span className="text-xs text-gray-400 mt-1 block">
                          (문제와 함께 다시 입력하거나, 에디터에서 문제를 수동 추가하세요)
                        </span>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {result.questions.map((q) => (
                          <QuestionCard
                            key={q.id}
                            question={q}
                            crossTypeResults={crossTypeResults[q.id] ?? []}
                            crossTypeLoading={crossTypeLoading[q.id] ?? false}
                            crossTypeError={crossTypeErrors[q.id] ?? null}
                            onCrossTypeCreate={handleCrossTypeCreate}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
