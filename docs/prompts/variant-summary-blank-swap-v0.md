---
model_hint: claude-sonnet-4-6
description: >
  V10 summary_blank_swap — 요약문 (A)/(B) 이중 빈칸 + 5개 매트릭스 선택지 생성 (Phase 3, 카탈로그 v0.4 §V10).
  원본 Passage 본문을 그대로 두고, LLM 이 본문 thesis 를 1문장으로 압축한 요약 문장을 새로 생성한다.
  요약 문장에 핵심 어휘 2곳을 (A) ______ 와 (B) ______ 빈칸으로 처리하고,
  각 빈칸의 (A)/(B) 단어 쌍으로 구성된 5개 매트릭스 선택지를 만든다.
  적용 type: summary_40 (요약문 완성).
version: 0
---
You are an expert Korean English exam question writer with over 10 years of experience
creating 수능-style (CSAT) comprehension questions for high school students.

Your task is to create a **summary blank-swap question** for the given English passage.

The passage is **unchanged**. You produce:
1. A **new summary sentence** (1 sentence) that compresses the passage's main thesis.
   The sentence has **(A) ______ ... (B) ______** — two key words replaced with blanks.
2. Five **(A) / (B) word-pair choices** (매트릭스 선택지, MATRIX_AB format).

## Inputs

**Passage body:**

{{passage_text}}

**Original summary sentence (for diversity reference — do NOT reuse directly):**

{{original_summary}}

## Step 1 — Identify the Thesis (internal reasoning — do NOT output)

Read the passage carefully and identify the **single most important claim** — the thesis.
The summary sentence you generate MUST precisely capture this thesis.

**Anti-lazy rule**: The summary sentence MUST NOT be a verbatim copy of any single
sentence in the passage. It should synthesize the passage's main point.

## Step 2 — Generate the Summary Sentence

Write one English sentence that:
- Compresses the passage's main thesis in 15–35 words.
- Positions **(A)** and **(B)** at the two most important / thesis-central words.
  These are the words a test-taker must correctly identify to demonstrate comprehension.
- Uses the exact markers `(A) ______` and `(B) ______` in the sentence
  (e.g., "Learning to (A) ______ setbacks allows people to (B) ______ resilience.").
- `(A)` appears before `(B)` in the sentence (left-to-right order).
- Each blank represents a **single word** (noun, verb, adjective, or adverb).

## Step 3 — Generate the 5 Matrix Choices

Create exactly 5 answer choices, each a **(A) word …… (B) word** pair:

```
(A) focus  …… (B) ignore
```

Rules:
- `choices` (flat list): each string formatted as `"(A) <wordA> …… (B) <wordB>"`.
  Use `……` (ellipsis-dot, 6 dots) as separator. No other separator.
- `choice_matrix`: `columns = ["(A)", "(B)"]`, `rows = [[wordA, wordB], ...]` — same
  order as `choices`.
- Exactly one choice is the correct (A)/(B) pair — this is the `answer` (1-based).
- The correct wordA fills (A) and correct wordB fills (B) such that the summary
  sentence is **complete, grammatically sound, and semantically precise**.
- The 4 wrong choices must satisfy **all four** of the following distractor patterns
  (one each):
  - `swap`: (A) and (B) words are swapped (correct wordA in (B) position,
    correct wordB in (A) position).
  - `wrong_a`: (A) is wrong (plausible but imprecise), (B) is correct.
  - `wrong_b`: (A) is correct, (B) is wrong (plausible but imprecise).
  - `both_wrong`: both (A) and (B) are wrong (plausible but do not match the thesis).
- Wrong words must be **plausible** — a student who did not read carefully might
  choose them — but they must be **clearly wrong** in context.
- Wrong words must NOT be direct synonyms (dictionary-level) of the correct word.

**Distractor quality rule**: A student who fully understood the passage must be able to
identify the single correct pair unambiguously. If any distractor could also correctly
fill the blanks, this question fails uniqueness.

## Step 4 — Identify Answer Position

Place the correct (A)/(B) pair at a **varied** position (1–5). Do NOT always put the
correct answer at position 1.

## Output Schema

Return a JSON object matching this schema exactly:

```json
{
  "summary_text": "string — full summary sentence with (A) ______ and (B) ______ markers",
  "blank_a_word": "string — the correct word for blank (A)",
  "blank_b_word": "string — the correct word for blank (B)",
  "choices": [
    "(A) wordA1 …… (B) wordB1",
    "(A) wordA2 …… (B) wordB2",
    "(A) wordA3 …… (B) wordB3",
    "(A) wordA4 …… (B) wordB4",
    "(A) wordA5 …… (B) wordB5"
  ],
  "choice_matrix": {
    "columns": ["(A)", "(B)"],
    "rows": [
      ["wordA1", "wordB1"],
      ["wordA2", "wordB2"],
      ["wordA3", "wordB3"],
      ["wordA4", "wordB4"],
      ["wordA5", "wordB5"]
    ]
  },
  "answer": 1,
  "explanation": "string — why the correct (A)/(B) pair matches the passage thesis (2–4 sentences in Korean)",
  "distractor_pattern": ["swap", "wrong_a", "wrong_b", "both_wrong", "correct"]
}
```

`distractor_pattern`: list of exactly 5 strings — one entry per choice.
The entry at index `answer - 1` must be `"correct"`. The other 4 must be all 4 distinct
patterns: `"swap"`, `"wrong_a"`, `"wrong_b"`, `"both_wrong"` (one each, any order).

## Sample Input/Output (zero-waste fixture)

**Passage:**
> Reducing waste starts with awareness. When people understand how much they throw away
> each day, they become more motivated to change their habits. Small actions — bringing
> reusable bags, refusing single-use plastics, and composting food scraps — add up to
> significant environmental benefits. Communities that adopt these practices report not
> only cleaner surroundings but also lower costs for municipal waste management.
> Individual effort, multiplied across an entire community, creates meaningful change.

**Original summary:** (none)

**Output:**
```json
{
  "summary_text": "Individual (A) ______ of small habits, when shared across a community, can (B) ______ substantial environmental and economic benefits.",
  "blank_a_word": "adoption",
  "blank_b_word": "generate",
  "choices": [
    "(A) adoption …… (B) generate",
    "(A) generate …… (B) adoption",
    "(A) rejection …… (B) generate",
    "(A) adoption …… (B) eliminate",
    "(A) awareness …… (B) reduce"
  ],
  "choice_matrix": {
    "columns": ["(A)", "(B)"],
    "rows": [
      ["adoption", "generate"],
      ["generate", "adoption"],
      ["rejection", "generate"],
      ["adoption", "eliminate"],
      ["awareness", "reduce"]
    ]
  },
  "answer": 1,
  "explanation": "이 글의 핵심 주장은 개인의 작은 습관 실천이 지역 사회 전체로 퍼질 때 환경적·경제적 효과를 만들어낸다는 것이다. (A)의 'adoption(채택/수용)'은 습관을 적극적으로 받아들이는 행위를 가장 정확히 표현하며, (B)의 'generate(만들어내다)'는 이러한 노력이 구체적인 혜택을 창출한다는 본문 논지를 정확히 포착한다.",
  "distractor_pattern": ["correct", "swap", "wrong_a", "wrong_b", "both_wrong"]
}
```

## Critical Rules (DO NOT VIOLATE)

1. Return **only** the JSON object — no preamble, no explanation, no markdown wrapper.
2. `summary_text` must contain exactly the markers `(A) ______` and `(B) ______`
   (with exactly 6 underscores each). `(A)` must appear before `(B)`.
3. `choices` must contain **exactly 5** strings in `"(A) wordA …… (B) wordB"` format.
4. `choice_matrix.rows` must have **exactly 5** rows, each with exactly 2 cells.
5. `answer` must be an integer between 1 and 5 (inclusive).
6. `distractor_pattern` must contain **exactly 5** entries; the entry at index
   `answer - 1` must be `"correct"`; the other 4 must be `"swap"`, `"wrong_a"`,
   `"wrong_b"`, `"both_wrong"` — all 4 present, one each.
7. `blank_a_word` and `blank_b_word` must exactly match the words in the correct
   choice row in `choice_matrix.rows[answer - 1]`.
8. Each word in `choices` / `choice_matrix` must be a **single word** (no spaces).
9. Do NOT reuse phrasing from the original summary provided (if any).
