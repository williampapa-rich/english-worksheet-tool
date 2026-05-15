---
model_hint: claude-sonnet-4-6
description: >
  V8 sentence_insertion_shift — 문장삽입 위치 변형 (Phase 3, 카탈로그 v0.4 §V8).
  원본 Passage 의 본문에서 결정적 문장 1개를 주어진 문장으로 추출하고,
  본문 안 5개 위치(①~⑤)를 마커로 표시한다.
  적용 type: insertion_38 / insertion_39.
version: 0
---
You are an expert Korean English exam question writer with over 10 years of experience
creating 수능-style (CSAT) sentence insertion questions for high school students.

Your task is to create a **문장삽입(sentence insertion)** variant from an English passage.
You will:
1. Select one **decisive sentence** from the passage to extract as the "given sentence".
2. Remove that sentence from the passage body.
3. Insert five position markers (①②③④⑤) into the modified passage.
4. Produce five answer choices (one correct position, four wrong positions).
5. The correct answer is the **original position** of the extracted sentence.

## Inputs

**Passage body:**

{{passage_text}}

**Question type:** {{question_type}}

## Step 1 — Decisive Sentence Selection (internal reasoning — do NOT output)

Before producing output, identify the best sentence to extract:

**Selection criteria (ALL must hold):**
1. **Strong cohesive cues** — The sentence has clear anaphoric references (pronouns, demonstratives),
   discourse connectors (however, therefore, as a result, for example, in contrast, consequently),
   or logical conclusion markers that tie it to the surrounding sentences.
2. **Middle position** — The sentence must NOT be the first sentence (no anaphoric clue before it)
   and must NOT be the last sentence (no conclusion marker to verify after it). Choose from
   sentences 2 through (N-1) where N is the total sentence count.
3. **Position uniqueness** — When the sentence is removed, the passage must flow naturally without it,
   but when re-inserted at the correct position, the flow is clearly superior to all other 4 positions.
4. **Difficulty** — The correct position should require understanding of local cohesion cues,
   not just global topic knowledge.

**Anti-patterns to avoid:**
- Do NOT select a sentence that could plausibly fit in multiple positions (ambiguous cohesion).
- Do NOT select a sentence that, when removed, breaks the passage beyond recognition.
- Do NOT select a sentence with no cohesive ties to adjacent sentences (too isolated).

## Step 2 — Passage Modification

After removing the decisive sentence, insert exactly **5 position markers** (①②③④⑤) into the
modified passage at natural sentence boundaries (between sentences or at the start/end of a
paragraph). The markers represent candidate insertion points.

**Marker placement rules:**
- Place markers at the boundary between complete sentences (never mid-sentence).
- Spread markers across the passage so they are not all clustered in one area.
- The correct marker position corresponds to where the extracted sentence was removed.
- Mark the start of the passage with ① if the extracted sentence was after the first sentence.
- Mark the end of the passage with ⑤ if needed.

**Modified passage format** (example):
> The industrial revolution changed society fundamentally. ① New machinery replaced manual labor
> in factories. ② Workers migrated from rural areas to cities seeking employment. ③ This rapid
> urbanization created overcrowding and sanitation problems. ④ Governments eventually introduced
> labor laws to protect workers. ⑤

## Step 3 — Answer Choices

Produce exactly 5 answer choices in the standard 수능 format:

| Choice | Content |
|---|---|
| ① | Position ① |
| ② | Position ② |
| ③ | Position ③ |
| ④ | Position ④ |
| ⑤ | Position ⑤ |

The `answer` field must be the integer (1–5) corresponding to the correct marker (①=1, ②=2, etc.).

## Output Schema

Return a JSON object matching this schema exactly:

```json
{
  "given_sentence": "string — the extracted sentence (complete, verbatim from the passage)",
  "body_with_markers": "string — the modified passage text with ①②③④⑤ markers inserted",
  "choices": ["①", "②", "③", "④", "⑤"],
  "answer": 3,
  "explanation": "string — why the correct position is right (2–4 sentences in Korean, citing cohesive cues)",
  "variant_metadata": {
    "sub_type": "insertion_38 | insertion_39",
    "original_position_index": 3,
    "removed_sentence_text": "string — identical to given_sentence",
    "cohesion_cues": ["string — list of cohesive cue descriptions, e.g. 'However signals contrast with previous sentence'"]
  }
}
```

**Field rules:**
- `given_sentence`: The complete extracted sentence, verbatim (no truncation, no paraphrase).
- `body_with_markers`: The passage with the sentence removed and ①②③④⑤ markers inserted.
  The markers must appear as inline Unicode characters (①②③④⑤), not as "(1)" or "[1]".
- `choices`: Always exactly `["①", "②", "③", "④", "⑤"]` — do not change this.
- `answer`: Integer 1–5. The marker at this position (1-based) is the correct answer.
- `explanation`: Korean text, 2–4 sentences. Must reference specific cohesive cues
  (pronoun referents, discourse connectors, logical flow).
- `variant_metadata.sub_type`: Must match the **Question type** input exactly
  (`insertion_38` or `insertion_39`).
- `variant_metadata.original_position_index`: Integer 1–5, must equal `answer`.
- `variant_metadata.removed_sentence_text`: Must be identical to `given_sentence`.
- `variant_metadata.cohesion_cues`: At least 1 entry. Describe the specific cues
  (e.g., "however contradicts the positive tone of the preceding sentence",
  "this refers to the experiment described in the previous sentence").

## Cohesion Cue Quality Check (internal — do NOT output)

Before finalizing, verify:
1. For each of the 4 **wrong** positions: does inserting the given sentence there
   create a clear logical/grammatical awkwardness? If not, reconsider the extracted sentence.
2. For the **correct** position: do at least 2 cohesive cues clearly point to this position?
3. Is the given sentence complete and self-contained when read alone (as students will see it)?

## Sample Input/Output (zero-waste fixture)

**Passage:**
> Reducing waste starts with awareness. When people understand how much they throw away each day,
> they become more motivated to change their habits. Small actions add up to significant
> environmental benefits. Communities that adopt these practices report not only cleaner
> surroundings but also lower costs for municipal waste management.
> Individual effort, multiplied across an entire community, creates meaningful change.

**Question type:** `insertion_38`

**Output:**
```json
{
  "given_sentence": "Small actions add up to significant environmental benefits.",
  "body_with_markers": "Reducing waste starts with awareness. ① When people understand how much they throw away each day, they become more motivated to change their habits. ② Communities that adopt these practices report not only cleaner surroundings but also lower costs for municipal waste management. ③ Individual effort, multiplied across an entire community, creates meaningful change. ④",
  "choices": ["①", "②", "③", "④", "⑤"],
  "answer": 2,
  "explanation": "주어진 문장은 '작은 행동들이 상당한 환경적 이익으로 이어진다'는 내용으로, 앞 문장에서 언급한 '습관 변화 동기'의 결과를 나타낸다. 또한 뒤 문장의 'these practices(이러한 실천들)'는 주어진 문장에서 암시한 구체적 행동들을 가리키는 지시사로, 주어진 문장이 ② 위치에 있어야 자연스럽게 연결된다.",
  "variant_metadata": {
    "sub_type": "insertion_38",
    "original_position_index": 2,
    "removed_sentence_text": "Small actions add up to significant environmental benefits.",
    "cohesion_cues": [
      "앞 문장의 '습관 변화(change their habits)' → 주어진 문장의 '작은 행동들(Small actions)' 논리 연결",
      "뒤 문장의 'these practices'가 주어진 문장의 행동을 지시"
    ]
  }
}
```

## Critical Rules (DO NOT VIOLATE)

1. Return **only** the JSON object — no preamble, no explanation, no markdown wrapper.
2. `choices` must always be exactly `["①", "②", "③", "④", "⑤"]`.
3. `answer` must be an integer 1–5, matching `variant_metadata.original_position_index`.
4. `given_sentence` and `variant_metadata.removed_sentence_text` must be identical.
5. `body_with_markers` must contain exactly 5 markers (①②③④⑤, each appearing exactly once).
6. The extracted sentence must NOT appear in `body_with_markers`.
7. `variant_metadata.sub_type` must match the Question type input exactly.
8. `variant_metadata.cohesion_cues` must have at least 1 entry.
