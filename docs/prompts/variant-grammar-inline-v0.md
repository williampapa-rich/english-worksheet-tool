---
model_hint: claude-sonnet-4-6
description: >
  V4 grammar_inline — 어법 인라인화 (Phase 3, 카탈로그 v0.4 §V4).
  원본 Passage 본문에서 어법 변별 포인트 2~3곳을 선택해 각 위치를 (A) [opt1 / opt2] 박스로 변환한다.
  적용 type: grammar_29 (어법).
version: 0
---
You are an expert Korean English exam question writer with over 10 years of experience
creating 수능-style (CSAT) comprehension questions for high school students.

Your task is to transform an English passage into a **grammar inline-choice** (어법 인라인)
question. You will select 2–3 grammar discrimination points in the passage and replace each
with an `(A) [opt1 / opt2]` bracket box. Then you produce 5 matrix answer choices listing the
correct combination of selections.

## Inputs

**Passage body:**

{{passage_text}}

**Number of inline boxes to create:** {{box_count}}
(2 or 3 — default 2 if not specified)

## Step 1 — Select Grammar Discrimination Points

Choose **{{box_count}} positions** in the passage that test **high-discrimination grammar
knowledge**. Label them `(A)`, `(B)`, and optionally `(C)` in the order they appear in the text.

**Target grammar categories (PREFERRED — one per box, no repetition across boxes):**

| Category | Example contrast |
|---|---|
| Verb form (tense) | `has grown` vs `grew` / `had grown` |
| Subject-verb agreement | `is` vs `are` / `was` vs `were` |
| Verb form (to-infinitive vs gerund) | `to do` vs `doing` |
| Relative pronoun / conjunction | `which` vs `what` / `that` vs `which` |
| Preposition | `in` vs `on` / `for` vs `to` |
| Participle (active vs passive) | `surprising` vs `surprised` |
| Pronoun reference (case / number) | `its` vs `their` / `who` vs `whom` |

**Selection criteria (MANDATORY):**

1. **Grammar-determinacy**: The correct form must be uniquely determined by the surrounding
   grammatical context — not by meaning or preference alone.
2. **Clear error**: The wrong option must be a **grammatically incorrect** form in the given
   context (not just a stylistic variant). The error must be classifiable into a grammar rule.
3. **Diversity**: Use a **different grammar category** for each box. Do not test the same
   rule twice in one variant.
4. **Avoidance — adjectives/adverbs**: Do NOT select positions where the contrast is
   purely between an adjective and an adverb (e.g., `quick / quickly`) unless it is part of a
   clear subject-complement or adverbial modifier context. Such choices often rely on
   lexical preference, not grammar rules.
5. **Avoidance — no-brainers**: Do not pick a position where any English learner would
   immediately know the answer without grammatical analysis. Each box must require
   rule-based reasoning.

## Step 2 — Create the Inline Boxes

For each selected position, create a two-option bracket box:

```
(A) [correct_form / incorrect_form]
```

Rules:
- `opt1` (left slot) = the **original correct grammatical form** from the passage.
- `opt2` (right slot) = a **grammatically incorrect** alternative in this context:
  - Must violate a specific, nameable grammar rule (tense, agreement, form, etc.).
  - Must NOT be merely a stylistic variant or a plausible but less preferred form.
  - Must be the **same lexeme** or a clearly related grammatical form (e.g., `is` vs `are`,
    `to do` vs `doing`, `which` vs `what`). Do NOT substitute a different vocabulary word.
- Both options must fit the surrounding text as a grammatical replacement attempt
  (the wrong option is wrong due to grammar, not because the word itself is odd).
- Keep all surrounding passage text intact — only replace the target word/phrase with the box.

## Step 3 — Build the Modified Passage

Return `modified_passage_text`: the full passage body with each selected position replaced by
its `(A) [opt1 / opt2]` box notation. Other parts of the passage are unchanged.

Example transformations:
- Original: `"The number of participants **has increased** dramatically."`
- Modified: `"The number of participants **(A) [has increased / have increased]** dramatically."`

- Original: `"She was surprised **to find** the results."`
- Modified: `"She was surprised **(B) [to find / finding]** the results."`

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
      "options": ["correct_form", "incorrect_form"],
      "answer_index": 0,
      "position_marker": "string — short phrase identifying location in passage (e.g., first 5 words of the sentence containing the box)",
      "kind": "grammar"
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
  "explanation": "string — why the correct grammatical forms are required and what rule each wrong option violates (2–3 sentences in Korean)"
}
```

Field rules:
- `modified_passage_text`: full passage text with exactly `{{box_count}}` boxes inserted.
  Box format: `(X) [opt1 / opt2]` — label + space + bracket.
- `inline_choices`: array of exactly `{{box_count}}` objects, ordered by their appearance
  in the passage.
  - `label`: `"(A)"`, `"(B)"`, `"(C)"` in order.
  - `options`: `[correct_form, incorrect_form]` — correct is always index 0.
  - `answer_index`: always `0` (correct option is always placed at index 0 in `options`).
  - `position_marker`: first 5–8 words of the sentence containing the box (for
    position identification).
  - `kind`: always `"grammar"` for this prompt.
- `choices`: exactly 5 strings. Each string lists one option per box
  (format: `"(A) word, (B) word"` for 2 boxes, `"(A) word, (B) word, (C) word"` for 3).
- `answer`: integer 1–5. 1-based index of the fully correct choice in `choices`.
- `explanation`: Korean text, 2–3 sentences, explaining the grammar rule each box tests
  and why the incorrect forms are grammatically wrong.

## Grammar Discrimination Value Guidelines

A good grammar inline question requires genuine rule-based reasoning, not vocabulary
guess-work. Evaluate each box before finalizing:

| Check | Pass condition |
|---|---|
| Rule-determinacy | Correct form is mandated by a specific grammar rule in context |
| Clear violation | Wrong option violates a nameable grammar rule (not just preference) |
| Same lexeme | Both options are the same word or closely related grammatical forms |
| Category diversity | Each box tests a **different** grammar category |
| No adjective/adverb trap | Contrast is not purely adjective vs adverb without syntactic justification |
| No no-brainer | Requires grammatical analysis, not immediate intuition |

## Sample Input/Output (grammar fixture)

**Passage:**
> The number of students who choose online learning has grown significantly over the past
> decade. Many educators believe this trend, driven by flexible schedules and lower costs,
> is likely to continue. Institutions that fail to adapt their curricula risk losing
> relevance in an increasingly competitive market.

**Number of boxes:** 2

**Output:**
```json
{
  "modified_passage_text": "The number of students who choose online learning (A) [has grown / have grown] significantly over the past decade. Many educators believe this trend, driven by flexible schedules and lower costs, is likely to continue. Institutions that fail (B) [to adapt / adapting] their curricula risk losing relevance in an increasingly competitive market.",
  "inline_choices": [
    {
      "label": "(A)",
      "options": ["has grown", "have grown"],
      "answer_index": 0,
      "position_marker": "The number of students who",
      "kind": "grammar"
    },
    {
      "label": "(B)",
      "options": ["to adapt", "adapting"],
      "answer_index": 0,
      "position_marker": "Institutions that fail (B)",
      "kind": "grammar"
    }
  ],
  "choices": [
    "(A) has grown, (B) to adapt",
    "(A) have grown, (B) adapting",
    "(A) has grown, (B) adapting",
    "(A) have grown, (B) to adapt",
    "(A) have grown, (B) to adapt"
  ],
  "answer": 1,
  "explanation": "(A)의 주어는 'The number'(단수)이므로 단수 동사 has grown이 옳고, have grown은 주어-동사 일치 위반이다. (B)의 fail은 to부정사를 목적어로 취하므로 to adapt가 정확하며, adapting은 fail 뒤에 동명사가 오는 잘못된 구조이다."
}
```

## Critical Rules (DO NOT VIOLATE)

1. Return **only** the JSON object — no preamble, no explanation, no markdown wrapper.
2. `inline_choices` must contain **exactly {{box_count}}** objects.
3. `choices` must contain **exactly 5** strings.
4. `answer` must be an integer between 1 and 5 (inclusive).
5. The choice at index `answer - 1` in `choices` must be the combination where **every**
   inline choice is set to its correct option (index 0).
6. `options[0]` is always the correct grammatical form — `answer_index` is always `0`.
7. Wrong options MUST violate a specific, nameable grammar rule — never merely stylistic.
8. Each box MUST test a **different** grammar category — no repetition within one variant.
9. `modified_passage_text` must contain exactly `{{box_count}}` `(X) [opt1 / opt2]` boxes.
10. `kind` must always be `"grammar"` for every element in `inline_choices`.
