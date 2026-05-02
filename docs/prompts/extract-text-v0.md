---
model_hint: claude-sonnet-4-6
description: >
  영어 지문/시험지 텍스트 → Passage + Question + Translation + Vocabulary 추출 (v0).
  텍스트 레이어 입력 전용. PM-5 (자료에 보이는 것만 추출), PM-6 (영어만이 default).
version: 0
---
You are an expert English language educator extracting structured information from Korean English exam materials.

Your task is to extract **only what is present in the source text** — do NOT generate, infer, or translate anything that is not already written.

## Input Text

{{input_text}}

## Extraction Rules

### Passages
- If the source contains **multiple separate passages** (e.g., a full exam paper with passages 18–40), extract each passage as a **separate item** in the `items` array.
- Preserve the original English text exactly — punctuation, capitalization, line breaks.
- Split the passage into logical `paragraphs` (one paragraph per element).
- Estimate or count the `word_count`.
- If a `target_grade` is mentioned (e.g., "고2", "high 2", "수능"), record it. Otherwise leave null.
- If a source provider is mentioned (e.g., "아잉카", "평가원", "EBSi"), record it in `source_provider`. Otherwise leave null.

### Questions
- Extract ALL exam questions that appear in the source.
- For each question, classify its `type` using **exactly one** of these 24 Korean English exam types:

  | Type value | Description |
  |---|---|
  | `purpose_18` | 목적 파악 (18번) |
  | `mood_19` | 심경·분위기 (19번) |
  | `assertion_20` | 주장 파악 (20번) |
  | `underline_implication_21` | 밑줄 함의 (21번) |
  | `gist_22` | 요지 파악 (22번) |
  | `theme_23` | 주제 파악 (23번) |
  | `title_24` | 제목 추론 (24번) |
  | `chart_25` | 도표 (25번) |
  | `figure_match_26` | 그림·일치 (26번) |
  | `notice_27` | 안내문 1 (27번) |
  | `notice_28` | 안내문 2 (28번) |
  | `grammar_29` | 어법 (29번) |
  | `vocabulary_30` | 어휘 (30번) |
  | `blank_phrase_31` | 빈칸 구 (31번) |
  | `blank_clause_32` | 빈칸 절 (32번) |
  | `blank_clause_33` | 빈칸 절 (33번) |
  | `blank_clause_34` | 빈칸 절 (34번) |
  | `irrelevant_sentence_35` | 무관문장 (35번) |
  | `order_36` | 순서배열 (36번) |
  | `order_37` | 순서배열 (37번) |
  | `insertion_38` | 문장삽입 (38번) |
  | `insertion_39` | 문장삽입 (39번) |
  | `summary_40` | 요약문 완성 (40번) |
  | `long_set_41_42` | 장문독해 세트 (41-42번) |
  | `long_set_43_45` | 장문독해 세트 (43-45번) |

- `stem`: the full question instruction text.
- `choices`: list of answer choices exactly as written (e.g., `["①", "②", "③", "④", "⑤"]` or full text choices).
- `correct_answer`: the answer if explicitly stated. Otherwise null.
- `explanation`: the explanation if present. Otherwise null.
- `number`: the question number if present (integer, e.g., 18, 29, 30).
- `sub_form`: use `"inline_choice"` if choices appear embedded in the passage body (e.g., `(A) [long-term / short-term]`). Use `"matrix_ab"` or `"matrix_abc"` for matrix-style choices. Otherwise null.

### Translation (한글 해석)
- **ONLY** extract if a Korean translation is **explicitly present** in the source.
- Do NOT generate a translation if none exists.
- If present, put the entire Korean translation text in `translation.text`.

### Vocabulary (어휘)
- **ONLY** extract if a vocabulary list or vocabulary box is **explicitly present** in the source.
- Do NOT generate vocabulary if none exists.
- For each vocabulary item: `headword` (the English word), `pos` (part of speech if stated), `meaning_ko` (Korean meaning if stated).

## Output Schema

Return a JSON object matching this schema exactly:

```json
{
  "items": [
    {
      "passage": {
        "body_text": "string — full English passage text",
        "paragraphs": ["string — paragraph 1", "string — paragraph 2"],
        "word_count": 120,
        "target_grade": "고2 or null",
        "topic_tags": ["science", "psychology"],
        "source_provider": "평가원 or null"
      },
      "questions": [
        {
          "type": "vocabulary_30",
          "stem": "다음 글의 밑줄 친 단어 중 ...",
          "choices": ["① accelerate", "② reduce", "③ maintain", "④ ignore", "⑤ enhance"],
          "correct_answer": "②",
          "explanation": null,
          "number": 30,
          "sub_form": null
        }
      ],
      "translation": null,
      "vocabulary": []
    }
  ]
}
```

## Critical Rules (DO NOT VIOLATE)

1. **Do NOT generate** Korean translations if none exist in the source.
2. **Do NOT generate** vocabulary lists if none exist in the source.
3. **Do NOT infer** answer choices — only extract what is explicitly written.
4. **Do NOT add** extra passages — only extract what exists in the source.
5. Every question `type` **must** be one of the 24 values in the table above.
6. If multiple passages exist in the source, include each as a **separate item** in the `items` array.
7. `translation: null` and `vocabulary: []` are the **normal default** for typical exam materials — this is expected, not an error.
