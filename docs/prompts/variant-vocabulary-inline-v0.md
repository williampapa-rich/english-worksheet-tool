---
model_hint: claude-sonnet-4-6
description: >
  V2 vocabulary_inline — 어휘 인라인화 (Phase 3, 카탈로그 v0.4 §V2).
  원본 Passage 본문에서 핵심 어휘 2~3곳을 선택해 각 위치를 (A) [opt1 / opt2] 박스로 변환한다.
  적용 type: vocabulary_30 (어휘), blank_phrase_31 (빈칸-구).
version: 0
---
You are an expert Korean English exam question writer with over 10 years of experience
creating 수능-style (CSAT) comprehension questions for high school students.

Your task is to transform an English passage into a **vocabulary inline-choice** (어휘 인라인)
question. You will select 2–3 key vocabulary positions in the passage and replace each with
an `(A) [opt1 / opt2]` bracket box. Then you produce 5 matrix answer choices listing the
correct combination of selections.

## Inputs

**Passage body:**

{{passage_text}}

**Number of inline boxes to create:** {{box_count}}
(2 or 3 — default 2 if not specified)

## Step 1 — Select Vocabulary Positions

Choose **{{box_count}} positions** in the passage that are **high-discrimination** vocabulary
words. Label them `(A)`, `(B)`, and optionally `(C)` in the order they appear in the text.

**Selection criteria (MANDATORY):**

1. **Semantic pivot words**: Choose adjectives or verbs whose replacement changes the
   passage's meaning meaningfully. Avoid articles, prepositions, and connectors.
2. **Context-determinacy**: The correct word must be clearly supported by the surrounding
   context — a student must read the whole passage to decide, not just the sentence.
3. **Distribution**: Do not pick words from the same sentence if possible. Spread across
   different clauses or sentences for variety.
4. **Avoidance — no-brainers**: Do not pick a word so obviously correct that any reader
   would immediately choose it without reading. Each box must require reasoning.

## Step 2 — Create the Inline Boxes

For each selected position, create a two-option bracket box:

```
(A) [correct_word / distractor_word]
```

Rules:
- `opt1` (left slot) = the **original correct word** from the passage (preserving form —
  tense, number, case).
- `opt2` (right slot) = a **plausible but contextually inappropriate** alternative:
  - Preferred: **antonym or semantically opposite** word (e.g., `increase / decrease`,
    `benefit / harm`, `support / undermine`).
  - Acceptable: a word that fits the grammatical slot but contradicts the passage's logic
    or tone.
  - **FORBIDDEN**: synonyms, near-synonyms, or words with overlapping contextual meaning.
    The distractor MUST be clearly wrong in context — not ambiguous.
- Both options must be the **same part of speech** and fit the grammatical frame of the
  sentence (same tense/number/form if applicable).
- Keep the surrounding passage text intact — only replace the target word with the box.

## Step 3 — Build the Modified Passage

Return `modified_passage_text`: the full passage body with each selected word replaced by
its `(A) [opt1 / opt2]` box notation. Other parts of the passage are unchanged.

Example transformation:
- Original: `"This strategy can **benefit** society as a whole."`
- Modified: `"This strategy can **(A) [benefit / harm]** society as a whole."`

## Step 4 — Create 5 Matrix Answer Choices

The student must choose one option from each box. The answer choices list the
**correct combination** and 4 incorrect combinations.

Format each choice as a comma-separated combination:
- 2 boxes: `"(A) opt1, (B) opt2"`
- 3 boxes: `"(A) opt1, (B) opt2, (C) opt1"`

Rules for the 5 choices:
- Exactly **1 correct choice** (all boxes set to their correct option).
- **4 incorrect choices** — each with at least one box set to the wrong option.
- All 5 choices must be **distinct**.
- Vary the position of the correct answer (do NOT always put it at choice 1).
- The 4 wrong choices should use different combinations of wrong options — avoid
  repeating the same error pattern across all 4 distractors.

## Output Schema

Return a JSON object matching this schema exactly:

```json
{
  "modified_passage_text": "string — full passage with (A) [opt1 / opt2] boxes inserted",
  "inline_choices": [
    {
      "label": "(A)",
      "options": ["correct_word", "distractor_word"],
      "answer_index": 0,
      "position_marker": "string — short phrase identifying location in passage (e.g., first 5 words of the sentence containing the box)",
      "kind": "vocabulary"
    }
  ],
  "choices": [
    "(A) opt1, (B) opt2",
    "(A) opt2, (B) opt1",
    "(A) opt1, (B) opt1",
    "(A) opt2, (B) opt2",
    "(A) opt1, (B) opt2"
  ],
  "answer": 1,
  "explanation": "string — why the correct options fit the passage context (2–3 sentences in Korean)"
}
```

Field rules:
- `modified_passage_text`: full passage text with exactly `{{box_count}}` boxes inserted.
  Box format: `(X) [opt1 / opt2]` — label + space + bracket.
- `inline_choices`: array of exactly `{{box_count}}` objects, ordered by their appearance
  in the passage.
  - `label`: `"(A)"`, `"(B)"`, `"(C)"` in order.
  - `options`: `[correct_word, distractor_word]` — correct is always index 0.
  - `answer_index`: always `0` (correct option is always placed at index 0 in `options`).
  - `position_marker`: first 5–8 words of the sentence containing the box (for
    position identification).
  - `kind`: always `"vocabulary"` for this prompt.
- `choices`: exactly 5 strings. Each string lists one option per box
  (format: `"(A) word, (B) word"` for 2 boxes, `"(A) word, (B) word, (C) word"` for 3).
- `answer`: integer 1–5. 1-based index of the fully correct choice in `choices`.
- `explanation`: Korean text, 2–3 sentences, explaining why the correct options are
  contextually appropriate and why the distractors are wrong.

## Discrimination Value Guidelines

A good vocabulary inline question requires genuine reading comprehension, not just
vocabulary look-up. Evaluate each box before finalizing:

| Check | Pass condition |
|---|---|
| Context-dependent | Correct answer cannot be determined from the single sentence alone |
| Semantic opposition | Distractor is semantically opposite or clearly contradictory in context |
| No synonym trap | Distractor is NOT a dictionary synonym of the correct word |
| Grammatical parity | Both options fit the grammatical frame (same POS, tense, number) |
| No repetition | The correct word does not appear verbatim elsewhere in a nearby sentence making it obvious |

## Sample Input/Output (zero-waste fixture)

**Passage:**
> Reducing waste starts with awareness. When people understand how much they throw away
> each day, they become more motivated to change their habits. Small actions — bringing
> reusable bags, refusing single-use plastics, and composting food scraps — add up to
> significant environmental benefits. Communities that adopt these practices report not
> only cleaner surroundings but also lower costs for municipal waste management.
> Individual effort, multiplied across an entire community, creates meaningful change.

**Number of boxes:** 2

**Output:**
```json
{
  "modified_passage_text": "Reducing waste starts with awareness. When people understand how much they throw away each day, they become more (A) [motivated / discouraged] to change their habits. Small actions — bringing reusable bags, refusing single-use plastics, and composting food scraps — add up to (B) [significant / negligible] environmental benefits. Communities that adopt these practices report not only cleaner surroundings but also lower costs for municipal waste management. Individual effort, multiplied across an entire community, creates meaningful change.",
  "inline_choices": [
    {
      "label": "(A)",
      "options": ["motivated", "discouraged"],
      "answer_index": 0,
      "position_marker": "they become more (A)",
      "kind": "vocabulary"
    },
    {
      "label": "(B)",
      "options": ["significant", "negligible"],
      "answer_index": 0,
      "position_marker": "add up to (B) environmental",
      "kind": "vocabulary"
    }
  ],
  "choices": [
    "(A) motivated, (B) significant",
    "(A) discouraged, (B) negligible",
    "(A) motivated, (B) negligible",
    "(A) discouraged, (B) significant",
    "(A) discouraged, (B) negligible"
  ],
  "answer": 1,
  "explanation": "글에서 사람들은 얼마나 버리는지 인식하면 습관을 바꾸려는 동기(motivated)가 생긴다고 서술되므로 (A)는 motivated가 적절하다. 작은 실천들이 모여 환경에 상당한(significant) 이점을 가져온다고 했으므로 (B)는 significant가 맞다. discouraged와 negligible은 글의 논리와 정반대 방향의 어휘로 문맥에 부적합하다."
}
```

## Critical Rules (DO NOT VIOLATE)

1. Return **only** the JSON object — no preamble, no explanation, no markdown wrapper.
2. `inline_choices` must contain **exactly {{box_count}}** objects.
3. `choices` must contain **exactly 5** strings.
4. `answer` must be an integer between 1 and 5 (inclusive).
5. The choice at index `answer - 1` in `choices` must be the combination where **every**
   inline choice is set to its correct option (index 0).
6. `options[0]` is always the correct word — `answer_index` is always `0`.
7. Distractors MUST be semantically opposite or clearly contradictory — never synonyms.
8. `modified_passage_text` must contain exactly `{{box_count}}` `(X) [opt1 / opt2]` boxes.
