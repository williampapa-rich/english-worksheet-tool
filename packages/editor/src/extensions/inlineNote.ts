/**
 * InlineNoteMark — 어휘 동의어 인라인 노트 extension (AnnotationKind.INLINE_NOTE)
 *
 * 본문 위 작은 글씨로 어휘 동의어를 표시한다 (예: "=foster, promote").
 * P1-2 에서 실제 렌더링 로직을 추가한다.
 *
 * 이 스텁 구현은 "등록 + 직렬화 라우팅" 만 제공한다.
 *
 * NOTE: AnnotationKind.INLINE_NOTE 의 TypeScript 미러 값 = "inline_note"
 * (shared/schemas/annotation.py AnnotationKind.INLINE_NOTE = "inline_note")
 * Python schema 변경 시 ANNOTATION_KIND 상수 파일도 동기화 필요.
 */
import { Mark, mergeAttributes } from "@tiptap/core";

export interface InlineNoteOptions {
  HTMLAttributes: Record<string, unknown>;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    inlineNote: {
      /**
       * 선택 범위에 인라인 노트를 설정한다.
       */
      setInlineNote: (attrs: {
        text: string;
        colorIndex?: number;
      }) => ReturnType;
      /**
       * 선택 범위의 인라인 노트를 해제한다.
       */
      unsetInlineNote: () => ReturnType;
    };
  }
}

export const InlineNoteMark = Mark.create<InlineNoteOptions>({
  name: "inlineNote",

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      text: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-inline-note-text"),
        renderHTML: (attributes) => {
          if (!attributes.text) return {};
          return { "data-inline-note-text": attributes.text as string };
        },
      },
      colorIndex: {
        default: null,
        parseHTML: (element) => {
          const v = element.getAttribute("data-inline-note-color");
          return v != null ? Number(v) : null;
        },
        renderHTML: (attributes) => {
          if (attributes.colorIndex == null) return {};
          return {
            "data-inline-note-color": String(attributes.colorIndex as number),
          };
        },
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-inline-note-text]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        "data-annotation-kind": "inline_note",
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setInlineNote:
        (attrs) =>
        ({ commands }) => {
          return commands.setMark(this.name, attrs);
        },
      unsetInlineNote:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name);
        },
    };
  },
});
