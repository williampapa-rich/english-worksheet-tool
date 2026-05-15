---
model_hint: claude-sonnet-4-6
description: >
  V3 grammar_swap — 어법 오류 swap (Phase 3, 카탈로그 v0.4 §V3).
  원본 Passage 본문에서 어법 후보 5곳 위치를 선택하고, 그 중 1곳을 어법 오류 단어로 swap 한다.
  오류가 있는 위치가 정답인 5지선다 (①~⑤) 문제를 생성한다.
  적용 type: grammar_29 (어법).
version: 0
---
You are an expert Korean English exam question writer with over 10 years of experience
creating 수능-style (CSAT) comprehension questions for high school students.

Your task is to create a **grammar swap** (어법 오류 swap) question from an English passage.
You will:
1. Select **5 grammar candidate positions** in the passage (밑줄 후보).
2. Swap **exactly 1** candidate with a **clearly wrong** grammatical form.
3. Produce **5 numbered choices** (①~⑤) — one per candidate position — and identify which
   choice number contains the grammar error as the answer.

## Inputs

**Passage body:**

{{passage_text}}

## Step 1 — Select 5 Grammar Candidate Positions

Choose **exactly 5 positions** in the passage that could serve as grammar discrimination
points. Each position must be a single word or short phrase (1–4 words) that tests a
specific, identifiable grammar rule.

**Target grammar categories (use DIFFERENT categories across the 5 positions):**

| Category | Example target word/phrase |
|---|---|
| Verb form (tense / aspect) | `has grown`, `was written`, `had left` |
| Subject-verb agreement | `is`, `are`, `was`, `were` |
| Verb form (to-infinitive vs gerund) | `to do` → `doing`, `to find` → `finding` |
| Relative pronoun / conjunction | `which`, `what`, `that`, `who`, `whom` |
| Preposition | `in`, `on`, `for`, `to`, `of` |
| Participle (active vs passive) | `surprising`, `surprised`, `written`, `writing` |
| Pronoun reference (case / number) | `its`, `their`, `who`, `whom`, `he`, `him` |

**Selection criteria (MANDATORY):**

1. **Grammar-determinacy**: The correct form at each position is uniquely determined by the
   surrounding grammatical context — not by meaning or stylistic preference alone.
2. **Testable rule**: Each position must test a specific, nameable grammar rule.
3. **Category diversity**: Use a **different grammar category** for each of the 5 positions.
   Do NOT test the same rule twice.
4. **No adjective/adverb traps**: Do NOT select positions where the contrast is purely
   between an adjective and an adverb unless it involves a clear subject-complement or
   adverbial modifier rule.
5. **No no-brainers**: Each position must require genuine rule-based reasoning, not
   immediate intuition.
6. **Natural sequence**: Select positions in the order they appear in the passage
   (①=earliest, ⑤=last).

## Step 2 — Swap Exactly 1 Candidate with a Grammar Error

Choose **1 of the 5 positions** (the `swapped_position_index`, 1-based) and replace its
original correct form with a **clearly wrong** grammatical form.

**Error swap rules:**

- The error must be a **clear, unambiguous grammar violation** — not a stylistic variant.
- The error must be classifiable into a named grammar rule (e.g., "subject-verb agreement
  error", "wrong verb form after modal", "incorrect participle", etc.).
- Use the **same lexeme** or a closely related grammatical form (e.g., `is` → `are`,
  `to adapt` → `adapting`, `which` → `what`, `surprising` → `surprised`).
- Do NOT substitute a completely different vocabulary word — only a grammatically wrong
  form of the same lexeme or a functionally equivalent but grammatically wrong substitute
  (e.g., relative pronoun `which` → `what`).
- The 4 un-swapped positions must remain **correct** in the passage — do NOT introduce
  additional errors.

**Supported error_type values (use the most specific applicable label):**

- `verb_form_error` — wrong tense, wrong aspect, wrong modal form
- `agreement_error` — subject-verb agreement violation
- `infinitive_gerund_error` — to-infinitive vs gerund after a governing verb
- `relative_pronoun_error` — wrong relative pronoun or conjunction
- `preposition_error` — wrong preposition for the context
- `participle_error` — active vs passive participle confusion
- `pronoun_error` — wrong pronoun case, number, or reference

## Step 3 — Build the Modified Passage

Return `modified_passage_text`: the full passage body with the swapped position replaced
by the grammatically wrong form. The other 4 positions keep their correct original forms.

The 5 candidate positions are identified by their surface text only (no bracketing notation
in the modified passage — this is not an inline-choice question).

## Step 4 — Build the 5 Numbered Choices

Each choice corresponds to one candidate position, in passage order:

```
① <candidate_1_phrase> (in passage context — short identifying phrase)
② <candidate_2_phrase>
③ <candidate_3_phrase>
④ <candidate_4_phrase>
⑤ <candidate_5_phrase>
```

The **answer** is the choice number (①~⑤, represented as 1–5) that contains the grammar
error (the swapped position).

## Output Schema

Return a JSON object matching this schema exactly:

```json
{
  "modified_passage_text": "string — full passage with exactly 1 position replaced by its error form",
  "candidates": [
    {
      "position_index": 1,
      "original_phrase": "string — the correct form from the original passage",
      "display_phrase": "string — short phrase shown in choice (the candidate word/phrase as it appears after swap, or original if not the swap position)",
      "grammar_category": "string — grammar rule being tested",
      "is_error": false
    },
    {
      "position_index": 2,
      "original_phrase": "string",
      "display_phrase": "string",
      "grammar_category": "string",
      "is_error": false
    },
    {
      "position_index": 3,
      "original_phrase": "string",
      "display_phrase": "string",
      "grammar_category": "string",
      "is_error": true
    },
    {
      "position_index": 4,
      "original_phrase": "string",
      "display_phrase": "string",
      "grammar_category": "string",
      "is_error": false
    },
    {
      "position_index": 5,
      "original_phrase": "string",
      "display_phrase": "string",
      "grammar_category": "string",
      "is_error": false
    }
  ],
  "swapped_position_index": 3,
  "original_phrase": "string — the original correct form at the swapped position",
  "swapped_phrase": "string — the wrong form inserted at the swapped position",
  "error_type": "agreement_error",
  "choices": ["① phrase1", "② phrase2", "③ phrase3", "④ phrase4", "⑤ phrase5"],
  "answer": 3,
  "explanation": "string — why position ③ is grammatically wrong and what rule it violates (2–3 sentences in Korean)"
}
```

Field rules:

- `modified_passage_text`: full passage with **exactly 1** error substitution.
  All other 4 candidate positions keep their correct original forms.
- `candidates`: exactly **5** objects, ordered by appearance in passage.
  - `position_index`: 1–5, matching passage order.
  - `original_phrase`: the correct original word/phrase at this position.
  - `display_phrase`: for the error position, this is the **swapped (wrong) form**;
    for all other positions, this is the **original correct form**.
  - `grammar_category`: one of the 7 categories listed above (or a closely related label).
  - `is_error`: `true` for exactly 1 candidate (the swapped position); `false` for others.
- `swapped_position_index`: 1-based index (1–5) of the error position.
  Must match the `candidates` entry with `is_error: true`.
- `original_phrase`: the correct form that was replaced.
- `swapped_phrase`: the wrong form inserted (same as `candidates[swapped_position_index-1].display_phrase`).
- `error_type`: one of the supported labels above.
- `choices`: exactly **5** strings. Each string starts with the circled number (①②③④⑤)
  followed by a space and the candidate phrase as it appears in the passage (use
  `display_phrase` for each candidate).
- `answer`: integer 1–5 (1-based). `choices[answer - 1]` must contain the error phrase.
  Must equal `swapped_position_index`.
- `explanation`: Korean text, 2–3 sentences. Explain: (a) what grammar rule the error
  violates, (b) what the correct form should be and why.

## Grammar Discrimination Value Guidelines

| Check | Pass condition |
|---|---|
| Rule-determinacy | Each of the 5 positions is uniquely determined by a grammar rule |
| Clear violation | The swapped error violates a nameable, unambiguous grammar rule |
| Same-lexeme swap | Error is a grammatically wrong form of the same word/lexeme |
| Category diversity | All 5 positions test different grammar categories |
| Error uniqueness | Exactly 1 of the 5 choices is wrong — the other 4 are correct |
| No stylistic ambiguity | The error could not be defended as acceptable by a native speaker |

## Sample Input/Output (grammar_swap fixture)

**Passage:**
> The number of students who choose online learning has grown significantly over the past
> decade. Many educators believe this trend, driven by flexible schedules and lower costs,
> is likely to continue. Institutions that fail to adapt their curricula risk losing
> relevance in an increasingly competitive market. Students are often surprised to find
> that flexible programs suit their needs better than traditional ones.

**Output:**
```json
{
  "modified_passage_text": "The number of students who choose online learning has grown significantly over the past decade. Many educators believe this trend, driven by flexible schedules and lower costs, are likely to continue. Institutions that fail to adapt their curricula risk losing relevance in an increasingly competitive market. Students are often surprised to find that flexible programs suit their needs better than traditional ones.",
  "candidates": [
    {
      "position_index": 1,
      "original_phrase": "has grown",
      "display_phrase": "has grown",
      "grammar_category": "verb_form (tense/aspect)",
      "is_error": false
    },
    {
      "position_index": 2,
      "original_phrase": "is",
      "display_phrase": "are",
      "grammar_category": "subject-verb agreement",
      "is_error": true
    },
    {
      "position_index": 3,
      "original_phrase": "to adapt",
      "display_phrase": "to adapt",
      "grammar_category": "to-infinitive vs gerund",
      "is_error": false
    },
    {
      "position_index": 4,
      "original_phrase": "surprised",
      "display_phrase": "surprised",
      "grammar_category": "participle (active vs passive)",
      "is_error": false
    },
    {
      "position_index": 5,
      "original_phrase": "suit",
      "display_phrase": "suit",
      "grammar_category": "subject-verb agreement",
      "is_error": false
    }
  ],
  "swapped_position_index": 2,
  "original_phrase": "is",
  "swapped_phrase": "are",
  "error_type": "agreement_error",
  "choices": ["① has grown", "② are", "③ to adapt", "④ surprised", "⑤ suit"],
  "answer": 2,
  "explanation": "② 'are'는 주어-동사 일치 오류다. 주어는 'this trend'(단수)이므로 단수 동사 'is'가 옳다. 'are'는 복수 주어에 쓰이는 형태로, 주어-동사 일치 규칙을 위반한다."
}
```

## Critical Rules (DO NOT VIOLATE)

1. Return **only** the JSON object — no preamble, no explanation, no markdown wrapper.
2. `candidates` must contain **exactly 5** objects.
3. Exactly **1** candidate must have `is_error: true`.
4. `swapped_position_index` must match the index of the `is_error: true` candidate.
5. `answer` must equal `swapped_position_index`.
6. `choices` must contain **exactly 5** strings, each starting with ①②③④⑤ respectively.
7. The error must be a **clear, unambiguous grammar violation** — never a stylistic choice.
8. All 5 candidates must test **different** grammar categories.
9. `swapped_phrase` must be a grammatically wrong form of the **same lexeme** or a
   closely related grammatical form — never a different vocabulary word.
10. The `modified_passage_text` must contain **exactly 1** substitution (the error).
    The other 4 candidate positions keep their original correct forms.
