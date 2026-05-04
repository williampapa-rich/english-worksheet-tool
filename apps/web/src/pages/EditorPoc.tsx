import {
  ArrowMark,
  BottomLabelMark,
  BracketMark,
  HighlightMark,
  InlineNoteMark,
  TopLabelMark,
  UnderlineMark,
  WordSnapExtension,
  annotationsToMarks,
  collectMarkRangesByAnnotationId,
  docToAnnotations,
} from "@english-worksheet-tool/editor";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useCallback, useEffect, useRef, useState } from "react";
import { HexColorPicker } from "react-colorful";
import { Link, useParams } from "react-router-dom";
import {
  AnalysisTable,
  type AnnotationChip,
  type LabelEntryKind,
} from "../components/AnalysisTable";
import { BracketEntryModal, type BracketStyleOption } from "../components/BracketEntryModal";
import type { BracketEditStyle } from "../components/ChipEditModal";
import { ChipEditModal } from "../components/ChipEditModal";
import { LabelEntryModal, type LabelEntryModalKind } from "../components/LabelEntryModal";
import { downloadPassageHwpx, getAnnotations, getPassage, replaceAnnotations } from "../lib/api";
import { buildChips } from "./buildChips";
import "./EditorPoc.css";

/**
 * EditorPoc — P1-2c 분석표 카테고리 재구조 에디터
 *
 * 변경 (vs P1-2b):
 *   - 툴바에서 top_label / bottom_label 버튼 제거 → 분석표 진입 버튼으로 이동
 *   - 툴바 category select 완전 제거
 *   - highlight / underline / bracket / arrow / inline_note → category: "note" 자동 주입
 *   - 분석표 진입 버튼 (성분/구/절) → bottom_label(sentence_role) / top_label(phrase|clause)
 *   - 진입 버튼 onMouseDown preventDefault 로 ProseMirror selection 보존
 *
 * 비DoD: API 통합, HWPX 다운로드, 컨텍스트 메뉴, 칩 클릭 강조.
 */

// ---------------------------------------------------------------------------
// 상수
// ---------------------------------------------------------------------------

// EXTENSIONS — mark 등록 순서가 ProseMirror DOM nesting 결정.
// 앞에 있는 mark = outer, 뒤에 있는 = inner.
// BracketMark 를 TopLabelMark 보다 앞에 두어 bracket 이 outer 가 되도록.
// → top_label 의 border-top 은 inner span 폭 (본문 텍스트만) 만 둘러쌈.
// → bracket 의 inline 괄호 글자는 outer span 안에서 layout 점유, 양옆 침범 없음.
const EXTENSIONS = [
  StarterKit,
  HighlightMark,
  UnderlineMark,
  BracketMark,
  TopLabelMark,
  BottomLabelMark,
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

// buildChips, extractDocText, truncate, KIND_PRIORITY — ./buildChips.ts 에서 import

// ---------------------------------------------------------------------------
// 컴포넌트
// ---------------------------------------------------------------------------

export function EditorPoc() {
  // URL param — passageId 있으면 API 로드 모드, 없으면 fixture 모드
  const { passageId } = useParams<{ passageId?: string }>();
  const isLoadMode = !!passageId;

  const [selectedColorIndex, setSelectedColorIndex] = useState<number | null>(1);
  const [customColor, setCustomColor] = useState<string | null>(null);
  const [showColorWheel, setShowColorWheel] = useState(false);
  const [pickerDraftHex, setPickerDraftHex] = useState("#ffffff");
  const colorWheelRef = useRef<HTMLDivElement>(null);
  const [serializedJson, setSerializedJson] = useState<string | null>(null);
  const [chips, setChips] = useState<AnnotationChip[]>([]);

  // API 로드 모드 전용 state
  const [loadState, setLoadState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; kind: "success" | "error" } | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 라벨 모달 상태 (성분/구/절 진입 버튼)
  const [modalState, setModalState] = useState<{
    open: boolean;
    entry: LabelEntryKind | null;
    pendingSelection: { from: number; to: number } | null;
  }>({ open: false, entry: null, pendingSelection: null });

  // 괄호 모달 상태 (툴바 괄호 버튼)
  const [bracketModalOpen, setBracketModalOpen] = useState(false);

  // 칩 수정 모달 상태
  const [chipEditState, setChipEditState] = useState<{
    open: boolean;
    chip: AnnotationChip | null;
  }>({ open: false, chip: null });

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
  // 토스트 헬퍼
  // ---------------------------------------------------------------------------

  /** showToast — 5초 후 자동 숨김. 기존 타이머 교체. */
  const showToast = useCallback((message: string, kind: "success" | "error") => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ message, kind });
    toastTimerRef.current = setTimeout(() => setToast(null), 5000);
  }, []);

  // ---------------------------------------------------------------------------
  // API 로드 모드 — passage + annotations 초기 로드
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!isLoadMode || !passageId || !editor) return;

    setLoadState("loading");
    setLoadError(null);

    void (async () => {
      try {
        const [passage, annotations] = await Promise.all([
          getPassage(passageId),
          getAnnotations(passageId),
        ]);

        // passage body_text → HTML 변환
        // paragraphs 가 있으면 각 단락을 <p> 로, 없으면 body_text 단일 <p>
        let html: string;
        if (passage.paragraphs && passage.paragraphs.length > 0) {
          html = passage.paragraphs.map((p) => `<p>${p}</p>`).join("");
        } else {
          html = `<p>${passage.body_text}</p>`;
        }

        // setContent — false = emit update event 안 함 (round-trip emit 폭주 방지)
        editor.commands.setContent(html, false);

        // annotation 역직렬화 — character offset → ProseMirror position
        // P1-6 follow-up: 다중 단락 paragraphLengths 전달 → 두번째 단락 이후
        // mark 위치도 정확. paragraphs 가 없으면 단일 body_text 단락 1개로 처리.
        if (annotations.length > 0) {
          const paragraphLengths =
            passage.paragraphs && passage.paragraphs.length > 0
              ? passage.paragraphs.map((p) => p.length)
              : [passage.body_text.length];
          const marks = annotationsToMarks(annotations, paragraphLengths);
          // race condition 방지 — 단일 setTimeout(0) 으로 setContent 완료 후 실행
          setTimeout(() => {
            let chain = editor.chain();
            for (const m of marks) {
              chain = chain
                .setTextSelection({ from: m.from, to: m.to })
                .setMark(m.markName, m.attrs);
            }
            chain.run();
          }, 0);
        }

        setLoadState("done");
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setLoadError(message);
        setLoadState("error");
      }
    })();
    // editor 는 mount 시 한 번만 실행 — passageId 변경 시 재실행
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoadMode, passageId, editor]);

  // ---------------------------------------------------------------------------
  // 핸들러 — 저장 (API 로드 모드 전용)
  // ---------------------------------------------------------------------------

  const handleSave = useCallback(async () => {
    if (!editor || !passageId) return;
    try {
      const doc = editor.getJSON();
      const annotations = docToAnnotations(doc);
      await replaceAnnotations(passageId, annotations);
      showToast("저장 완료", "success");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast(`저장 실패: ${message}`, "error");
    }
  }, [editor, passageId, showToast]);

  /**
   * handleDownloadHwpx — Phase 1 DoD #3 와이프 검수용 HWPX 다운로드.
   *
   * 현재 에디터 상태를 먼저 저장한 뒤 backend 가 DB 의 annotation 을 기반으로
   * 렌더한 HWPX 파일을 다운로드한다. 미저장 변경이 있으면 다운로드 결과에
   * 반영되지 않으므로 항상 저장 → 다운로드 순서.
   */
  const handleDownloadHwpx = useCallback(async () => {
    if (!editor || !passageId) return;
    try {
      // 1) 현재 에디터 상태 저장 (미저장 변경 반영)
      const doc = editor.getJSON();
      const annotations = docToAnnotations(doc);
      await replaceAnnotations(passageId, annotations);

      // 2) HWPX 다운로드 트리거
      await downloadPassageHwpx(passageId);
      showToast("HWPX 다운로드 완료", "success");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast(`다운로드 실패: ${message}`, "error");
    }
  }, [editor, passageId, showToast]);

  // 색상 휠 팝오버 outside click 감지
  useEffect(() => {
    if (!showColorWheel) return;
    function handleOutside(e: MouseEvent) {
      if (colorWheelRef.current && !colorWheelRef.current.contains(e.target as Node)) {
        setShowColorWheel(false);
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [showColorWheel]);

  // doc 변경 감지 → chips 갱신
  useEffect(() => {
    if (!editor) return;
    const updateChips = () => {
      const doc = editor.getJSON();
      const initialChips = buildChips(doc);

      // spanText 를 ProseMirror doc.textBetween 으로 재계산.
      // buildChips 의 character offset slice 는 단일 단락 가정 (annotationSerializer
      // pmPosToCharOffset = pmPos - 2) — 다중 단락 / 단어 경계 / mark range 끝 계산에서
      // 마지막 글자가 누락되는 케이스 발생. ProseMirror mark range 직접 사용으로 회피.
      const pmDoc = editor.state.doc;
      const annotationIdToRange = new Map<string, { from: number; to: number }>();
      pmDoc.descendants((node, pos) => {
        if (!node.isText) return;
        for (const mark of node.marks) {
          const annId = (mark.attrs.annotationId as string | null | undefined) ?? null;
          if (!annId) continue;
          const start = pos;
          const end = pos + node.nodeSize;
          const existing = annotationIdToRange.get(annId);
          if (!existing) {
            annotationIdToRange.set(annId, { from: start, to: end });
          } else {
            // 같은 annotationId 의 split 조각 — 범위 확장
            annotationIdToRange.set(annId, {
              from: Math.min(existing.from, start),
              to: Math.max(existing.to, end),
            });
          }
        }
      });

      const refinedChips = initialChips.map((chip) => {
        const range = annotationIdToRange.get(chip.annotationId);
        if (!range) return chip;
        const rawText = pmDoc.textBetween(range.from, range.to, "\n");
        const truncated =
          rawText.length <= 30
            ? rawText
            : `${rawText.slice(0, Math.ceil(29 / 2))}…${rawText.slice(rawText.length - Math.floor(29 / 2))}`;
        return { ...chip, spanText: truncated };
      });

      setChips(refinedChips);
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

  /** 현재 활성 색 hex 반환 — customColor 우선, 없으면 palette */
  function resolveHighlightHex(): string {
    if (customColor !== null) return customColor;
    const palette = COLOR_PALETTE.find((c) => c.index === selectedColorIndex);
    return palette?.hex ?? "#fef08a";
  }

  /** colorIndex 정수 반환 — customColor 모드(palette 선택 해제)면 1로 fallback */
  function resolveColorIndex(): number {
    return selectedColorIndex ?? 1;
  }

  /**
   * trimSelection — 현재 selection 의 양 끝 공백을 제거한 from/to 반환.
   * mark 가 양 끝 blank 까지 그어지는 시각 버그 해결 (PM 폴리싱).
   * trim 후 길이가 0 이면 null (적용 무효).
   */
  function trimSelection(): { from: number; to: number } | null {
    if (!editor) return null;
    const { from, to } = editor.state.selection;
    if (from === to) return null;
    const text = editor.state.doc.textBetween(from, to);
    const leftTrim = text.length - text.trimStart().length;
    const rightTrim = text.length - text.trimEnd().length;
    const newFrom = from + leftTrim;
    const newTo = to - rightTrim;
    if (newFrom >= newTo) return null;
    return { from: newFrom, to: newTo };
  }

  const handleHighlight = () => {
    if (!editor) return;
    const trimmed = trimSelection();
    if (!trimmed) return;
    const color = resolveHighlightHex();
    const annotationId = crypto.randomUUID();
    const colorIndex = resolveColorIndex();
    // 툴바 5종 → category: "note" 자동 주입
    editor
      .chain()
      .focus()
      .setTextSelection(trimmed)
      .setMark("highlight", { color, annotationId, category: "note", colorIndex })
      .run();
  };

  const handleUnderline = () => {
    if (!editor) return;
    const trimmed = trimSelection();
    if (!trimmed) return;
    const annotationId = crypto.randomUUID();
    const colorIndex = resolveColorIndex();
    editor
      .chain()
      .focus()
      .setTextSelection(trimmed)
      .setMark("underline", { annotationId, category: "note", colorIndex })
      .run();
  };

  const handleBracket = () => {
    if (!editor) return;
    const trimmed = trimSelection();
    if (!trimmed) {
      alert("텍스트를 먼저 선택해주세요.");
      return;
    }
    // 모달 열기 — 실제 mark 적용은 handleBracketModalSubmit 에서
    setBracketModalOpen(true);
  };

  const handleBracketModalSubmit = useCallback(
    (style: BracketStyleOption) => {
      if (!editor) return;
      const { from, to } = editor.state.selection;
      const text = editor.state.doc.textBetween(from, to);
      const leftTrim = text.length - text.trimStart().length;
      const rightTrim = text.length - text.trimEnd().length;
      const trimmedFrom = from + leftTrim;
      const trimmedTo = to - rightTrim;
      if (trimmedFrom >= trimmedTo) return;
      const annotationId = crypto.randomUUID();
      const colorIdx = selectedColorIndex ?? 1;
      editor
        .chain()
        .focus()
        .setTextSelection({ from: trimmedFrom, to: trimmedTo })
        .setBracket({
          bracketStyle: style,
          colorIndex: colorIdx,
          category: "note",
          annotationId,
        })
        .run();
    },
    [editor, selectedColorIndex]
  );

  const handleArrow = () => {
    if (!editor) return;
    const trimmed = trimSelection();
    if (!trimmed) return;
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
      .setTextSelection(trimmed)
      .setArrow({
        arrowTargetStart: targetStart,
        arrowTargetEnd: targetEnd,
        colorIndex: resolveColorIndex(),
        category: "note",
        annotationId,
      })
      .run();
  };

  const handleInlineNote = () => {
    if (!editor) return;
    const trimmed = trimSelection();
    if (!trimmed) return;
    const text = prompt("인라인 노트 텍스트를 입력하세요 (예: =foster, promote):");
    if (!text) return;
    const annotationId = crypto.randomUUID();
    editor
      .chain()
      .focus()
      .setTextSelection(trimmed)
      .setInlineNote({
        text,
        colorIndex: resolveColorIndex(),
        category: "note",
        annotationId,
      })
      .run();
  };

  // 삭제는 분석표 칩 x 로만 (PM 결정) — 툴바 unset 핸들러 제거됨.

  // ---------------------------------------------------------------------------
  // 핸들러 — 분석표 진입 버튼 (성분/구/절)
  // ---------------------------------------------------------------------------

  /**
   * handleLabelEntry — AnalysisTable 진입 버튼 콜백.
   *
   * onMouseDown 에서 preventDefault 로 ProseMirror selection 을 보존한 뒤
   * onClick 에서 이 콜백이 호출된다.
   * selection 을 modalState.pendingSelection 에 저장하고 모달을 연다.
   * 실제 mark 적용은 modal onSubmit 에서 수행.
   */
  const handleLabelEntry = useCallback(
    (entry: LabelEntryKind) => {
      if (!editor) return;

      // selection 양 끝 공백 trim 적용
      const { from, to } = editor.state.selection;
      if (from === to) {
        alert("텍스트를 먼저 선택해주세요.");
        return;
      }
      const text = editor.state.doc.textBetween(from, to);
      const leftTrim = text.length - text.trimStart().length;
      const rightTrim = text.length - text.trimEnd().length;
      const trimmedFrom = from + leftTrim;
      const trimmedTo = to - rightTrim;
      if (trimmedFrom >= trimmedTo) {
        alert("선택 영역이 비어있습니다.");
        return;
      }

      // trim 된 selection 저장 후 모달 open
      setModalState({
        open: true,
        entry,
        pendingSelection: { from: trimmedFrom, to: trimmedTo },
      });
    },
    [editor]
  );

  /**
   * handleModalSubmit — 모달 확인 시 mark 적용.
   *
   * pendingSelection 으로 setTextSelection 후 mark 를 적용한다.
   * bracketStyle 이 있으면 동일 span 에 bracket mark 도 동시 적용.
   */
  const handleModalSubmit = useCallback(
    (params: { text: string; bracketStyle: "()" | "{}" | "[]" | null }) => {
      if (!editor || !modalState.entry || !modalState.pendingSelection) return;

      const { from, to } = modalState.pendingSelection;
      const entry = modalState.entry;
      const annotationId = crypto.randomUUID();

      const colorIdx = selectedColorIndex ?? 1;

      if (entry.markKind === "bottom_label") {
        editor
          .chain()
          .focus()
          .setTextSelection({ from, to })
          .setBottomLabel({
            text: params.text,
            colorIndex: colorIdx,
            category: entry.category,
            annotationId,
          })
          .run();
      } else {
        // top_label (구/절)
        let chain = editor.chain().focus().setTextSelection({ from, to }).setTopLabel({
          text: params.text,
          colorIndex: colorIdx,
          category: entry.category,
          annotationId,
        });

        // 괄호 옵션 선택 시 bracket mark 도 같은 span 에 동일 annotationId 로 적용
        // → 분석표에서 칩 1개로 dedup (KIND_PRIORITY: top_label > bracket)
        if (params.bracketStyle) {
          chain = chain.setBracket({
            bracketStyle: params.bracketStyle,
            colorIndex: colorIdx,
            category: entry.category,
            annotationId,
          });
        }
        chain.run();
      }

      setModalState({ open: false, entry: null, pendingSelection: null });
    },
    [editor, modalState, selectedColorIndex]
  );

  const handleModalClose = useCallback(() => {
    setModalState({ open: false, entry: null, pendingSelection: null });
  }, []);

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
  // 핸들러 — 칩 클릭 (수정 모달 열기)
  // ---------------------------------------------------------------------------

  const handleChipClick = useCallback((chip: AnnotationChip) => {
    // arrow 는 수정 불가 — AnnotationChipView 에서 이미 필터링되나 방어적으로도 체크
    if (chip.kind === "arrow") return;
    setChipEditState({ open: true, chip });
  }, []);

  /**
   * handleChipEditSave — 칩 수정 모달 저장 시 mark attrs 갱신.
   *
   * 같은 annotationId 의 모든 mark range 를 수집 → 각 range 를 unset → set 으로
   * attrs 를 새 값으로 교체한다.
   * bracket mark (top_label 과 annotationId 공유) 처리:
   *   - bracketStyle 이 null 로 변경 → bracket mark 범위 unset
   *   - bracketStyle 이 값이 있을 때 bracket range 가 없으면 새로 set 불가
   *     (selection 정보가 없으므로). 이 케이스는 현재 수정 불가 — 원래 괄호 없이
   *     저장된 top_label 에 추후 괄호 추가는 별도 케이스.
   */
  const handleChipEditSave = useCallback(
    (params: {
      annotationId: string;
      text?: string;
      colorIndex: number | null;
      bracketStyle: BracketEditStyle | null;
    }) => {
      if (!editor) return;

      const ranges = collectMarkRangesByAnnotationId(editor.state.doc, params.annotationId);
      if (ranges.length === 0) return;

      // 기존 mark 의 category 를 보존하기 위해 attrs 사전 수집
      // (chain unset → set 사이에서 category 정보 유지 — 누락되면 분석표에서 행 매칭 실패)
      const categoryByMark = new Map<string, string | null>();
      const doc = editor.state.doc;
      doc.descendants((node) => {
        if (!node.isText) return;
        for (const mark of node.marks) {
          const annId = (mark.attrs.annotationId as string | null | undefined) ?? null;
          if (annId !== params.annotationId) continue;
          const cat = (mark.attrs.category as string | null | undefined) ?? null;
          if (!categoryByMark.has(mark.type.name)) {
            categoryByMark.set(mark.type.name, cat);
          }
        }
      });

      let chain = editor.chain();

      for (const r of ranges) {
        // 기존 mark attrs 를 유지하면서 새 값으로 교체
        const markName = r.markName;
        const preservedCategory = categoryByMark.get(markName) ?? null;

        if (markName === "bracket") {
          if (params.bracketStyle === null) {
            // bracketStyle 제거 → bracket mark unset
            chain = chain.setTextSelection({ from: r.from, to: r.to }).unsetMark(markName);
          } else {
            // bracketStyle 갱신
            chain = chain
              .setTextSelection({ from: r.from, to: r.to })
              .unsetMark(markName)
              .setBracket({
                bracketStyle: params.bracketStyle,
                colorIndex: params.colorIndex ?? 1,
                category: preservedCategory,
                annotationId: params.annotationId,
              });
          }
        } else if (markName === "topLabel") {
          chain = chain
            .setTextSelection({ from: r.from, to: r.to })
            .unsetMark(markName)
            .setTopLabel({
              text: params.text ?? "",
              colorIndex: params.colorIndex ?? undefined,
              category: preservedCategory,
              annotationId: params.annotationId,
            });
        } else if (markName === "bottomLabel") {
          chain = chain
            .setTextSelection({ from: r.from, to: r.to })
            .unsetMark(markName)
            .setBottomLabel({
              text: params.text ?? "",
              colorIndex: params.colorIndex ?? undefined,
              category: preservedCategory,
              annotationId: params.annotationId,
            });
        } else if (markName === "inlineNote") {
          chain = chain
            .setTextSelection({ from: r.from, to: r.to })
            .unsetMark(markName)
            .setInlineNote({
              text: params.text ?? "",
              colorIndex: params.colorIndex ?? undefined,
              category: preservedCategory,
              annotationId: params.annotationId,
            });
        } else if (markName === "highlight") {
          const hex =
            params.colorIndex != null
              ? (COLOR_PALETTE.find((c) => c.index === params.colorIndex)?.hex ?? "#fef08a")
              : "#fef08a";
          chain = chain
            .setTextSelection({ from: r.from, to: r.to })
            .unsetMark(markName)
            .setMark("highlight", {
              color: hex,
              colorIndex: params.colorIndex,
              annotationId: params.annotationId,
              category: preservedCategory ?? "note",
            });
        } else if (markName === "underline") {
          chain = chain
            .setTextSelection({ from: r.from, to: r.to })
            .unsetMark(markName)
            .setMark("underline", {
              colorIndex: params.colorIndex,
              annotationId: params.annotationId,
              category: preservedCategory ?? "note",
            });
        }
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
  // active 상태 (툴바 5종)
  // ---------------------------------------------------------------------------

  const isHighlightActive = editor?.isActive("highlight") ?? false;
  const isUnderlineActive = editor?.isActive("underline") ?? false;
  const isBracketActive = editor?.isActive("bracket") ?? false;
  const isArrowActive = editor?.isActive("arrow") ?? false;
  const isInlineNoteActive = editor?.isActive("inlineNote") ?? false;

  // ---------------------------------------------------------------------------
  // 렌더
  // ---------------------------------------------------------------------------

  // entryKind 도출 — entry.category 가 LabelEntryModalKind 와 1:1
  const modalKind: LabelEntryModalKind =
    modalState.entry?.markKind === "bottom_label"
      ? "sentence_role"
      : ((modalState.entry?.category as LabelEntryModalKind | undefined) ?? "phrase");

  // 로드 모드 + 로딩 중 — 에디터 전체 대신 로딩 화면 반환
  if (isLoadMode && loadState === "loading") {
    return (
      <main className="min-h-screen bg-gray-50 p-8 flex items-center justify-center">
        <p className="text-gray-500 text-sm">로딩 중...</p>
      </main>
    );
  }

  // 로드 모드 + 에러
  if (isLoadMode && loadState === "error") {
    return (
      <main className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-4xl mx-auto">
          <Link to="/" className="text-blue-600 hover:underline text-sm">
            ← 홈으로
          </Link>
          <p className="mt-4 text-red-600 text-sm">
            지문 로드 실패: {loadError ?? "알 수 없는 오류"}
          </p>
        </div>
      </main>
    );
  }

  return (
    <>
      <LabelEntryModal
        open={modalState.open}
        entryKind={modalKind}
        onSubmit={handleModalSubmit}
        onClose={handleModalClose}
      />
      <BracketEntryModal
        open={bracketModalOpen}
        onSubmit={handleBracketModalSubmit}
        onClose={() => setBracketModalOpen(false)}
      />
      <ChipEditModal
        open={chipEditState.open}
        chip={chipEditState.chip}
        bracketStyle={chipEditState.chip?.bracketStyle ?? null}
        onSave={handleChipEditSave}
        onRemove={handleRemoveAnnotation}
        onClose={() => setChipEditState({ open: false, chip: null })}
      />
      {/* 토스트 알림 (5초 자동 숨김) */}
      {toast && (
        <output
          className={[
            "fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium transition-all",
            toast.kind === "success"
              ? "bg-green-50 border border-green-200 text-green-800"
              : "bg-red-50 border border-red-200 text-red-800",
          ].join(" ")}
          aria-live="polite"
        >
          {toast.message}
        </output>
      )}
      <main className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* 헤더 */}
          <div className="flex items-center gap-4">
            <Link to="/" className="text-blue-600 hover:underline text-sm">
              ← 홈으로
            </Link>
            <h1 className="text-xl font-bold text-gray-900">구문분석 에디터 드래프트 (P1-2c)</h1>
            <span className="text-xs text-gray-400 bg-yellow-100 px-2 py-0.5 rounded">
              드래프트 — PM 검수용
            </span>
            {isLoadMode && (
              <span className="text-xs text-blue-500 bg-blue-50 px-2 py-0.5 rounded">
                API 모드 — passage {passageId}
              </span>
            )}
          </div>

          {/* 에디터 + 분석표 영역 */}
          <div className="flex flex-col gap-4">
            {/* 에디터 카드 */}
            <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
              {/* 툴바 그룹 1: annotation 적용 버튼 (5종 — 메모 카테고리 자동 매핑) */}
              <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 space-y-2">
                <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                  Annotation (메모 자동 매핑)
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
                    label="괄호"
                    active={isBracketActive}
                    disabled={!editor}
                    onClick={handleBracket}
                  />
                  <AnnotationButton
                    label="화살표"
                    active={isArrowActive}
                    disabled={!editor}
                    onClick={handleArrow}
                  />
                  <AnnotationButton
                    label="노트"
                    active={isInlineNoteActive}
                    disabled={!editor}
                    onClick={handleInlineNote}
                  />
                </div>
              </div>

              {/* 툴바 그룹 2: color_index picker (12색 swatch + 무지개 휠) */}
              <div className="px-4 py-2 border-b border-gray-100 bg-gray-50 flex items-center gap-3">
                <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide whitespace-nowrap">
                  색상
                </span>
                <div className="flex flex-wrap gap-1 items-center">
                  {COLOR_PALETTE.map((c) => (
                    <button
                      key={c.index}
                      type="button"
                      title={`색 ${c.index} (${c.label})`}
                      onClick={() => {
                        setSelectedColorIndex(c.index);
                        setCustomColor(null);
                        setShowColorWheel(false);
                      }}
                      className={[
                        "w-5 h-5 rounded-full border-2 transition-transform",
                        selectedColorIndex === c.index && customColor === null
                          ? "border-gray-700 scale-125"
                          : "border-transparent hover:scale-110",
                      ].join(" ")}
                      style={{ backgroundColor: c.hex }}
                    />
                  ))}

                  {/* 무지개 색상 휠 버튼 */}
                  <div className="relative" ref={colorWheelRef}>
                    <button
                      type="button"
                      title="자유 색상 (highlight only)"
                      onClick={() => {
                        setShowColorWheel((v) => !v);
                        if (!showColorWheel) {
                          setPickerDraftHex(customColor ?? "#ffffff");
                        }
                      }}
                      className={[
                        "w-5 h-5 rounded-full border-2 transition-transform overflow-hidden",
                        customColor !== null
                          ? "border-gray-700 scale-125"
                          : "border-transparent hover:scale-110",
                      ].join(" ")}
                      style={{
                        background: "conic-gradient(red, yellow, lime, cyan, blue, magenta, red)",
                      }}
                      aria-label="자유 색상 휠 열기"
                    />
                    {showColorWheel && (
                      <div
                        className="absolute top-7 left-0 z-50 bg-white rounded-xl shadow-xl border border-gray-200 p-3 flex flex-col gap-2"
                        style={{ minWidth: 200 }}
                      >
                        <HexColorPicker color={pickerDraftHex} onChange={setPickerDraftHex} />
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-gray-500 font-mono flex-1">
                            {pickerDraftHex}
                          </span>
                          <button
                            type="button"
                            className="px-2 py-1 text-xs font-semibold bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
                            onClick={() => {
                              setCustomColor(pickerDraftHex);
                              setSelectedColorIndex(null);
                              setShowColorWheel(false);
                            }}
                          >
                            적용
                          </button>
                        </div>
                        <p className="text-xs text-gray-400 leading-snug">
                          * 자유 색상은 형광펜(highlight)에만 적용됩니다. 다른 annotation 은 기본
                          팔레트로 대체됩니다.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
                <span className="text-xs text-gray-400">
                  {customColor !== null ? `자유: ${customColor}` : `선택: #${selectedColorIndex}`}
                </span>
              </div>

              {/* 툴바 제어: 직렬화 / 초기화 / 저장 */}
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
                {/* 저장 버튼 — API 로드 모드 전용 */}
                {isLoadMode && (
                  <button
                    type="button"
                    onClick={() => void handleSave()}
                    disabled={!editor}
                    className="px-3 py-1.5 text-sm font-medium rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 hover:bg-emerald-100 transition-colors disabled:opacity-50 ml-auto"
                  >
                    저장
                  </button>
                )}
                {/* HWPX 다운로드 버튼 — API 로드 모드 전용 (P1-9) */}
                {isLoadMode && (
                  <button
                    type="button"
                    onClick={() => void handleDownloadHwpx()}
                    disabled={!editor}
                    className="px-3 py-1.5 text-sm font-medium rounded-lg bg-blue-50 border border-blue-200 text-blue-700 hover:bg-blue-100 transition-colors disabled:opacity-50"
                  >
                    HWPX 다운로드
                  </button>
                )}
              </div>

              {/* Tiptap 에디터 본문 */}
              <EditorContent editor={editor} />
            </div>

            {/* 분석표 (본문 에디터 하단) */}
            <AnalysisTable
              chips={chips}
              onRemove={handleRemoveAnnotation}
              onLabelEntry={handleLabelEntry}
              onChipClick={handleChipClick}
            />
          </div>

          {/* 사용 안내 */}
          <p className="text-xs text-gray-400 leading-relaxed">
            텍스트를 선택 후 annotation 버튼 (형광펜/밑줄/괄호/화살표/노트) 을 클릭하면 메모
            카테고리로 자동 분류됩니다. 성분/구/절 라벨은 분석표 진입 버튼으로 추가하세요 (텍스트
            선택 후 버튼 클릭). 칩을 클릭하면 수정 모달이 열립니다. ✕ 버튼으로 즉시 삭제.
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
    </>
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
}

function AnnotationButton({ label, active, disabled, onClick }: AnnotationButtonProps) {
  // 삭제는 분석표 칩 x 로만 — 툴바 버튼은 추가 전용 (PM 결정).
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
    </span>
  );
}
