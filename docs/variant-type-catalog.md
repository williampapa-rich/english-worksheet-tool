# 변형 유형 카탈로그 v0.4 — 24개 유형 인벤토리 + sub-form + VariantKind enum 정합

- **작성자**: domain-expert agent
- **작성일**: 2026-05-02 (v0.1~v0.3) / 2026-05-15 (v0.4 갱신)
- **버전**: v0.4
- **이전 버전**:
  - v0.1 (2026-05-02) — "5개 변형 유형을 별 카테고리로 정의"라는 잘못된 전제로 작성됨, 폐기.
  - v0.2 (2026-05-02) — 24개 유형 + sub-form + variant_kind 골격 완성. type 코드는 한국어명만 명시.
  - v0.3 (2026-05-02) — 각 24개 유형에 snake_case 영문 enum value 후보 컬럼 추가.
- **v0.4 변경** (2026-05-15, ADR-0017 Accepted 후속):
  - §3.2 V1~V10 각 항목에 **`shared/schemas/question.py` `VariantKind` enum value** 명시 — 카탈로그 ID 와 enum 멤버 1:1 정합.
  - V6 `topic_main_idea_swap` — v0.3 의 enum `THEME_REWORD` → `TOPIC_MAIN_IDEA_SWAP` 으로 통합 (V6 명세가 요지/주제/제목 3개 type 을 포함하므로 enum 명도 정합 갱신).
  - §3.4 1순위 표 갱신 — V2/V4/V5/V6/V7 (5개) Phase 3 진입 시 LLM 프롬프트 작성 대상.
  - **§3.5 신규** — LLM 변형 프롬프트 사전 가이드 (ADR-0013 augment 패턴 참고, 실제 프롬프트는 Phase 3 별 PR).
  - **§3.6 신규** — qa-validator 검증 시나리오 (ADR-0017 D3-c 하이브리드 — `Question.uniqueness_validated` 최신 상태 + `qa_validation_results` history 정합).
- **정정 사유 (v0.1 → v0.2 시점)**: `CLAUDE.md` v0.3 §6.2에서 PM이 전제를 정정 — **변형 유형이라는 별 카테고리는 없다**. 모든 문제 유형은 `exam-generator`의 24개 유형 중 하나에 속한다. Phase 3의 "변형문제"도 기존 유형의 **파생**일 뿐, 새 유형이 아니다. 5개만 추리지 않고 **24개 모두 1급**으로 다룬다.
- **관련 문서**:
  - `CLAUDE.md` v0.3 §6.2 (Question 유형 — 별도 카테고리가 아니라 기존 유형의 확장)
  - `docs/adr/_pm-decisions-sprint-0.md` (PM D-1, D-2, D-3)
  - `docs/adr/0017-question-variant-table-strategy.md` (Accepted, 2026-05-15) — 단일 `Question` 테이블 + `variant_kind` discriminator 채택. 본 v0.4 의 enum 보강과 짝 (D2-b 결정).
  - `docs/adr/0013-llm-augmentation-pipeline.md` (Phase 2 보강 파이프라인) — Phase 3 변형 프롬프트의 모태 패턴.
  - `docs/schema-coverage-audit.md` (architect, 2026-05-02)
  - `docs/audit-review-domain.md` (domain-expert v0.1)
  - `docs/reference-program-analysis.md` (PM, 영상 레퍼런스 6종 annotation)
  - `~/workspace/exam-generator/shared/schemas/question.py:69-80` (`ACTIVE_TYPES`)
  - `~/workspace/exam-generator/app/llm/prompts.py:99-319` (`TYPE_HINTS`)

---

## 0. 본 카탈로그의 위치와 사용법

본 카탈로그는 `Question.type` enum의 1차 source이며, architect의 작업 #5(`shared/schemas/` v0.1) 입력으로 들어간다.

**구조**:
- **§1**: exam-generator 24개 유형의 도메인 인벤토리 (출제 의도 / 표면 형태 / 입출력 매핑 / 검증 기준)
- **§2**: 자료 sweep으로 발견되는 sub-form (Gap A 본문 내장 어휘 / Gap B 매트릭스 등) — 어느 type의 sub-form인지 매핑
- **§3**: Phase 3 변형 생성에서의 variant_kind 후보 — 같은 type 안의 파생
- **§4**: Annotation kind 카탈로그 — 영상 레퍼런스 6종 (구문분석 도메인)
- **§5**: 미해결 / 추가 조사 필요 항목

**확실/추정 표기 컨벤션**:
- 출처가 exam-generator 코드 또는 평가원 표준에서 확인 가능한 사실은 **확실**.
- 한국 학원 시장 일반론·강사 추정은 **추정**으로 표시.
- 와이프 인터뷰 또는 PM 결정이 필요한 항목은 §5에 등록.

---

## 1. exam-generator 24개 유형 인벤토리

### 1.1 24개 유형 enum (확실, exam-generator 코드 직접 추출)

출처: `~/workspace/exam-generator/shared/schemas/question.py:69-80` (`ACTIVE_TYPES` tuple, 도표(25)는 `DISABLED_TYPES`로 비활성).

**컬럼 설명**:
- **표시명 (한국어)**: exam-generator의 `ACTIVE_TYPES` 그대로. UI 표시·legacy 호환용.
- **enum value 후보 (snake_case)**: `Question.type` Pydantic enum의 영문 코드. **architect 결정 위임** — domain은 후보 제시만. 평가원 번호 suffix가 동일 대분류 다중 슬롯(빈칸-절 32/33/34, 순서배열 36/37, 문장삽입 38/39)을 구분하는 데 필수.
- **레이아웃**: `LAYOUT_PATTERN` (`question.py:38-63`) 기준 6종 중 하나.

| # | 표시명 (한국어) | enum value 후보 (snake_case) | 평가원 번호 | 대분류 | 레이아웃 | 본문 마커 | 비고 |
|---|---|---|---|---|---|---|---|
| 1 | `목적(18)` | `purpose_18` | 18 | 추론형 (편지) | letter_box | 없음 | 편지/공고 형식 5~7문장 |
| 2 | `심경(19)` | `mood_19` | 19 | 추론형 (서사) | reasoning | 없음 | 1인칭 서사 |
| 3 | `주장(20)` | `claim_20` | 20 | 추론형 (논설) | reasoning | 없음 | 논설문 4~6문장 |
| 4 | `밑줄함의(21)` | `underline_implication_21` | 21 | 추론형 | reasoning | `_..._` 1개 | 밑줄 표현의 함의 |
| 5 | `요지(22)` | `main_idea_22` | 22 | 추론형 | reasoning | 없음 | 한국어 단문 보기 |
| 6 | `주제(23)` | `topic_23` | 23 | 추론형 | reasoning | 없음 | 영어 명사구 보기 |
| 7 | `제목(24)` | `title_24` | 24 | 추론형 | reasoning | 없음 | 영어 제목 보기 |
| 8 | `인물일치(26)` | `figure_match_26` | 26 | 사실형 | reasoning | **마커 일체 금지** | 인물 약력 5~7문장 |
| 9 | `안내문(27)` | `notice_mismatch_27` | 27 | 사실형 (박스) | letter_box | 없음 | 행사 안내문 (불일치) |
| 10 | `안내문(28)` | `notice_match_28` | 28 | 사실형 (박스) | letter_box | 없음 | 27과 동형 / 정·역 변형 가능 |
| 11 | `어법(29)` | `grammar_29` | 29 | 어법 | marker_inline | `①_w_ ... ⑤_w_` | 5개 단어/구 어법 판별 |
| 12 | `어휘(30)` | `vocabulary_30` | 30 | 어휘 | marker_inline | `①_w_ ... ⑤_w_` | 5개 낱말 문맥 적절성 |
| 13 | `빈칸-구(31)` | `blank_phrase_31` | 31 | 빈칸추론 | blank_inline | `______` 1개 | 명사구 빈칸 |
| 14 | `빈칸-절(32)` | `blank_clause_32` | 32 | 빈칸추론 | blank_inline | `______` 1개 | 절 빈칸 |
| 15 | `빈칸-절(33)` | `blank_clause_33` | 33 | 빈칸추론 | blank_inline | `______` 1개 | 32와 동형 |
| 16 | `빈칸-절(34)` | `blank_clause_34` | 34 | 빈칸추론 | blank_inline | `______` 1개 | 32와 동형 |
| 17 | `무관문장(35)` | `irrelevant_sentence_35` | 35 | 논리 | marker_inline | `①~⑤` 5개 | 도입 + ①②③④⑤ 5문장 |
| 18 | `순서배열(36)` | `paragraph_order_36` | 36 | 논리 (단락) | passage_segments | `(A)/(B)/(C)` 라벨 (시스템 후처리) | 주어진 글 + 3단락 |
| 19 | `순서배열(37)` | `paragraph_order_37` | 37 | 논리 (단락) | passage_segments | 동일 | 36과 동형 |
| 20 | `문장삽입(38)` | `sentence_insertion_38` | 38 | 논리 | marker_inline | `①~⑤` 위치 마커 | given_sentence 별도 |
| 21 | `문장삽입(39)` | `sentence_insertion_39` | 39 | 논리 | marker_inline | 동일 | 38과 동형 |
| 22 | `요약문(40)` | `summary_40` | 40 | 논리 (요약 박스) | passage_segments | summary `(A) ______ ... (B) ______` | 빈칸 2개 |
| 23 | `장문(41-42)` | `long_set_41_42` | 41-42 | 장문 세트 | long_set | `(a)~(e)` 라벨 | 41=제목 + 42=어휘 |
| 24 | `장문독해(43-45)` | `long_reading_43_45` | 43-45 | 장문 세트 | long_set | `(a)~(e)` + `(A)~(D)` 라벨 | 43=순서 + 44=지칭 + 45=일치 |

비활성: `도표(25)` (`chart_25` 후보) — 이미지 생성 미지원으로 exam-generator에서 disabled. 본 프로젝트도 v0.1에선 동일하게 미지원.

**enum value 명명 컨벤션 (architect 검토 권고)**:
- snake_case + 평가원 번호 suffix.
- 대분류 다중 슬롯은 번호로 구분 (`blank_clause_32`, `_33`, `_34`).
- 장문 세트는 hyphen 대신 underscore (`long_set_41_42`).
- 영문 단어 선택은 한국 영어 시험 출제 도메인의 표준 영문 표현 (예: 요지=main_idea, 어법=grammar, 어휘=vocabulary).
- **architect 영역**: 본 후보를 받아들일지, 다른 명명 (예: 평가원 번호 prefix `p18_purpose`, 또는 enum 그대로 한글 유지) 채택할지는 architect 결정. domain은 영문 코드를 권고 — 코드 가독성 + Python typing 호환.

### 1.2 유형별 상세 — 출제 의도 / 표면 형태 / 입출력 / 검증 기준

각 유형의 출제 의도는 `app/llm/prompts.py`의 `TYPE_HINTS`에서 직접 추출 (확실). 검증 기준 중 일부는 한국 영어 출제 도메인의 일반 통념(추정).

#### (1) `목적(18)` — 글의 목적

- **출제 의도**: 편지·공고·안내문에서 발신자의 의도(부탁/안내/요청 등)를 추론. 형식 인지 + 핵심 발화 의도 파악.
- **표면 형태**:
  - question_text: "다음 글의 목적으로 가장 적절한 것은?"
  - passage: 편지/공고 형식. 첫 줄 "Dear ...", 마지막 "Sincerely," + 이름.
  - choices: 한국어 단문 5개 (`~을 안내하기 위해`, `~을 요청하기 위해` 형식, 원문자 없이).
- **본문 마커**: 없음. exam-generator 분류는 `letter_box` 레이아웃 (`question.py:39`).
- **원본 → 정규화**: 입력이 이미 18번 형식이면 1:1. 본 프로젝트에선 `Passage.body_text`(정제 본문) + `Question(type="목적(18)", choices=[5개 한국어])`.
- **검증 기준**:
  - 정답 유일성: 4개 오답이 본문 일부 사실에 근거하지만 전체 의도와는 어긋나야 함.
  - 흔한 실패 모드: 본문이 너무 짧으면 의도가 명백, 너무 길면 여러 의도 혼재.
- **출처**: `app/llm/prompts.py:101-107`.

#### (2) `심경(19)` — 주인공의 심경 / 심경 변화

- **출제 의도**: 1인칭 서사에서 주인공의 감정 변화를 추론. 서사 분위기·어휘 단서 파악.
- **표면 형태**:
  - question_text: "다음 글에 드러난 [I/주인공]의 심경[변화]로 가장 적절한 것은?"
  - passage: 1인칭 서사.
  - choices: 영어 형용사 한 쌍 (`relieved → indifferent` 형식).
- **본문 마커**: 없음. 레이아웃 `reasoning`.
- **검증 기준**:
  - 5개 형용사 쌍이 의미적으로 변별 가능해야 함 (synonym pair는 회피).
  - 본문에 양쪽 감정의 단서가 모두 있어야 (변화형의 경우).
- **출처**: `app/llm/prompts.py:108-113`.

#### (3) `주장(20)` — 필자의 주장

- **출제 의도**: 논설문에서 필자가 강하게 내세우는 주장(should/must 류) 추론.
- **표면 형태**:
  - question_text: "다음 글에서 필자가 주장하는 바로 가장 적절한 것은?"
  - passage: 논설문 4~6문장.
  - choices: 한국어 단문 (`~해야 한다` 형식).
- **검증 기준**:
  - 정답이 본문의 결론(thesis) 문장과 정렬.
  - 오답은 본문 예시·세부에서 너무 narrow하게 추출되거나 too-broad 일반화.
- **출처**: `app/llm/prompts.py:114-118`.

#### (4) `밑줄함의(21)` — 밑줄 친 표현의 함의

- **출제 의도**: 본문 안의 비유적/암시적 표현이 문맥에서 갖는 함의 추론.
- **표면 형태**:
  - question_text: "밑줄 친 [영어 표현]이 다음 글에서 의미하는 바로 가장 적절한 것은?"
  - passage 안 `_..._` 정확히 1개 (LLM 직접 출력).
  - **글자 단위 일치 강제**: 본문 토큰과 question_text 인용이 정확히 일치 (대소문자/시제/단복수까지).
  - choices: 한국어 또는 영어 단문 5개.
- **본문 마커**: `_..._` 1개. 레이아웃 `reasoning`.
- **원본 → 정규화**: 마커 분리 모델(audit Gap K) 적용 시, `_word_`는 `Passage.body_text`에서 분리되고 별도 `Annotation(kind="marker_underline", span=...)`으로 표현. question_text의 인용은 span에서 자동 추출.
- **검증 기준**:
  - **인용 일치**: 본문 밑줄 텍스트 == question_text 인용 (글자 단위).
  - 함의 추출이 비유적 해석을 요구해야 함 (직역 회피).
- **출처**: `app/llm/prompts.py:119-130`.

#### (5) `요지(22)` — 글의 요지

- **출제 의도**: 본문 전체 메시지를 한 문장으로 압축. 한국 영어 시험 변별력 핵심 유형 중 하나.
- **표면 형태**:
  - question_text: "다음 글의 요지로 가장 적절한 것은?"
  - passage: 논설/설명문.
  - choices: 한국어 단문 (`~이다` 형식).
- **검증 기준**:
  - 정답이 본문 thesis와 정확히 일치.
  - 오답: too-narrow / too-broad / 본문 표현 변형해서 결론 반대 / 무관 그럴듯.
- **출처**: `app/llm/prompts.py:131-135`.

#### (6) `주제(23)` — 글의 주제

- **출제 의도**: 본문이 다루는 주제를 영어 명사구로 압축.
- **표면 형태**:
  - question_text: "다음 글의 주제로 가장 적절한 것은?"
  - choices: 영어 명사구 (`the importance of ~` 형식, 6~12 단어 추정).
- **검증 기준**:
  - 영어 명사구의 문법적 형식 준수 (보통 정관사 the로 시작, 동사 시작 회피).
  - 22번/24번과의 차이: 22는 결론 문장, 23은 주제 명사구, 24는 짧은 제목.
- **출처**: `app/llm/prompts.py:136-140`.

#### (7) `제목(24)` — 글의 제목

- **출제 의도**: 본문에 가장 적합한 제목.
- **표면 형태**:
  - choices: 영어 제목 형식 (대문자 첫 글자, 4~10 단어, 종종 `Title: Subtitle` 또는 의문문).
- **검증 기준**:
  - 제목 형식 준수.
  - 본문 핵심을 압축하되 너무 평이하지 않은 (출제 학년 수준의 변별력).
- **출처**: `app/llm/prompts.py:141-145`.

#### (8) `인물일치(26)` — 인물 약력 일치

- **출제 의도**: 인물의 약력 사실 진술 5개 중 본문과 모순되는 1개 찾기.
- **표면 형태**:
  - question_text: "[인물 이름]에 관한 다음 글의 내용과 일치하지 않는 것은?"
  - passage: 인물 약력 5~7문장. **마커 일체 금지** (`_..._` / `①②③④⑤` / `______` 모두).
  - choices: 한국어 사실 진술 (`~에서 태어났다`).
- **본문 마커**: **명시적 금지**. 도메인 관점에서 마커 시스템과의 충돌 케이스.
- **검증 기준**:
  - 정확히 1개만 본문과 모순.
  - 4개 진술은 본문 사실 그대로(literal) 또는 자연스러운 paraphrase.
- **출처**: `app/llm/prompts.py:148-156`.

#### (9) `안내문(27)` — 행사 안내문 (불일치)

- **출제 의도**: 행사/카드/프로그램 안내문의 사실 정보 5개 중 본문과 일치하지 않는 1개 찾기.
- **표면 형태**:
  - **박스 안에 표시**: 큰 제목 + 헤딩 라인(`When & Where`, `What to Bring`) + 항목.
  - passage[0]: 큰 제목 (가운데 정렬). passage[1..]: 헤딩과 항목.
  - choices: 한국어 사실 진술.
- **본문 마커**: 없음. 레이아웃 `letter_box`. exam-generator는 `TYPES_WITH_BOX_PASSAGE`로 박스 처리 (`question.py:102`).
- **검증 기준**:
  - 본문에 가격/날짜/조건 등 구체적 정보가 풍부해야 오답 만들기 쉬움.
- **출처**: `app/llm/prompts.py:157-165`.

#### (10) `안내문(28)` — 행사 안내문 (일치 또는 27과 정·역)

- **출제 의도**: 27과 동형이지만 다른 행사. **27이 "일치하지 않는" 형태면 28은 "일치하는" 형태로 정·역 변형도 가능**.
- **표면 형태**: 27과 동일.
- **출처**: `app/llm/prompts.py:166-171`.

#### (11) `어법(29)` — 어법 판별

- **출제 의도**: 본문 5곳의 단어/구가 어법(시제/관계사/동명사 vs to부정사/분사/일치 등)상 옳은지 판단. 5개 중 1개만 틀림.
- **표면 형태**:
  - question_text: "다음 글의 밑줄 친 부분 중, 어법상 틀린 것은?"
  - passage 안 `①_to부정사_ ... ②_분사구_ ... ⑤_시제_` 정확히 5개 마커.
  - choices: `["①","②","③","④","⑤"]` 평탄 5개.
  - answer: 틀린 번호 (1~5).
- **본문 마커**: `①~⑤` + `_..._` 동시 사용. 레이아웃 `marker_inline`.
- **검증 기준**:
  - 5개 어법 포인트가 다양해야 함 (전부 시제만은 학습 가치 떨어짐).
  - 회색지대 문법(예: 비제한적 관계사 that/which) 회피 — 정답 모호 위험.
- **흔한 실패 모드**:
  - 두 옵션이 모두 문법적으로 가능한 회색지대.
  - 미국식/영국식 차이로 판정이 갈리는 케이스 (한국 시험은 미국식 표준).
- **출처**: `app/llm/prompts.py:174-181`.

#### (12) `어휘(30)` — 낱말의 문맥상 적절성

- **출제 의도**: 본문 5곳의 단어가 문맥상 적절한지 판단. **단순 dictionary 의미가 아니라 본문의 논리·tone과 정합**하는지가 핵심.
- **표면 형태**: 어법(29)과 동형. 마커도 동일.
- **검증 기준**:
  - 부적절한 단어는 본문 의미를 명확히 어긋나게 만들어야 함 (반의어 또는 의미 충돌어 사용 일반적).
  - 4개 적절한 단어는 dictionary 동의어로 swap 가능한 변별 가치 있는 위치.
  - 정답 유일성 위험: 두 단어가 모두 문맥상 가능한 경우 가장 흔한 실패.
- **출처**: `app/llm/prompts.py:182-188`.

#### (13) `빈칸-구(31)` — 명사구 빈칸

- **출제 의도**: 본문 1곳의 핵심 명사구를 빈칸으로 비우고 문맥상 적절한 표현 선택. 글의 흐름·논리 추론.
- **표면 형태**:
  - question_text: "다음 빈칸에 들어갈 말로 가장 적절한 것은?"
  - passage 안 `______` 정확히 1개 (언더스코어 6개).
  - choices: 영어 명사구/형용사구 5개.
- **본문 마커**: `______` 1개. 레이아웃 `blank_inline`.
- **검증 기준**:
  - 빈칸 위치가 본문 thesis 문장의 핵심 어구.
  - 오답 4개는 본문 표현 변형 또는 본문 일부와 의미적으로 관련되되 빈칸 위치에 부적합.
- **흔한 실패 모드**:
  - 정답이 본문 다른 곳에 그대로 등장 (literal repetition — 추론이 아니라 검색).
  - 빈칸이 너무 짧음 (1단어) → 어휘 문제로 변질.
- **출처**: `app/llm/prompts.py:191-198`.

#### (14)~(16) `빈칸-절(32)` / `빈칸-절(33)` / `빈칸-절(34)` — 절 빈칸

- **출제 의도**: 빈칸-구(31)와 동일하나 빈칸이 절(clause) 단위. 한국 영어 시험 최고 난이도 유형 중 하나.
- **표면 형태**: 31과 동형이되 choices는 영어 절 (보통 10~25 단어).
- **검증 기준**:
  - **연결어 처리**: 본문 `that ______`처럼 연결어가 빈칸 직전에 있으면 choices에 그 연결어 **포함하지 않음**.
  - 31과 동일 다른 기준.
- **32 vs 33 vs 34**: 평가원 형식상 동일 유형 3개 슬롯. 본 프로젝트에선 type 코드로는 구분되지만, 표면 형태·변형 규칙은 같다.
- **출처**: `app/llm/prompts.py:199-211`.

#### (17) `무관문장(35)` — 흐름과 무관한 문장

- **출제 의도**: 본문 5문장 중 흐름과 무관한 1개 찾기. 글의 응결성(cohesion) 파악.
- **표면 형태**:
  - question_text: "다음 글에서 전체 흐름과 관계 없는 문장은?"
  - passage: `[도입(번호 없음), ①문장1, ②문장2, ③무관, ④문장4, ⑤문장5]` 6원소.
  - choices: `①~⑤`.
- **본문 마커**: `①~⑤` 5개. 레이아웃 `marker_inline`.
- **검증 기준**:
  - 무관 문장은 본문 주제와 관련 있어 보이되 논리 흐름에서 벗어나야 함 (완전 무관은 너무 명백).
  - 4개 정상 문장이 인접 문장 간 응결 단서(접속사/대명사/정관사)로 연결.
- **출처**: `app/llm/prompts.py:215-221`.

#### (18) `순서배열(36)` — 단락 순서 배열

- **출제 의도**: "주어진 글" 다음에 (A)/(B)/(C) 단락의 자연스러운 순서. 단락 간 응결 단서 추적.
- **표면 형태**:
  - question_text: "주어진 글 다음에 이어질 글의 순서로 가장 적절한 것은?"
  - passage: 주어진 글 1단락 (200~300자).
  - sub_passages: `[[A단락], [B단락], [C단락]]` (라벨 없이 본문만 — 시스템이 (A)/(B)/(C) 라벨 후처리).
  - choices: 정확히 `["(A)-(C)-(B)", "(B)-(A)-(C)", "(B)-(C)-(A)", "(C)-(A)-(B)", "(C)-(B)-(A)"]` 5개.
  - **반드시 괄호 포함 형식** `(X)-(Y)-(Z)` (괄호 없는 `B-A-C` 금지).
- **본문 마커**: 시스템이 (A)/(B)/(C) 라벨 후처리 부착 (LLM은 평문). 레이아웃 `passage_segments`.
- **검증 기준**:
  - 응결 단서 충분 — 각 단락 시작/끝에 다음 단락 가리키는 단서.
  - 단락 길이 균형 (학생이 길이 추측으로 못 풀게).
  - 정답 분포 편향 위험 (exam-generator의 Hotfix 17-2 참조 — `_recent_answers_directive`로 회피).
- **출처**: `app/llm/prompts.py:222-232`, `_apply_alpha_markers` (`generator.py:221-238`).

#### (19) `순서배열(37)` — 36과 동형

- 동일 형식, 다른 주제. 출처: `app/llm/prompts.py:233`.

#### (20) `문장삽입(38)` — 주어진 문장 삽입 위치

- **출제 의도**: 주어진 문장이 본문 ①~⑤ 위치 중 어디에 들어갈지. 문맥 단절·재연결 단서 파악.
- **표면 형태**:
  - question_text: "글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 적절한 곳은?"
  - given_sentence: 영어 문장 1개 (시스템이 박스로 감쌈).
  - passage 안 `①②③④⑤` 5개 위치 마커.
  - choices: `①~⑤`.
- **본문 마커**: `①~⑤` 5개. 레이아웃 `marker_inline`.
- **출처**: `app/llm/prompts.py:234-242`.

#### (21) `문장삽입(39)` — 38과 동형

- 출처: `app/llm/prompts.py:243`.

#### (22) `요약문(40)` — 요약문 빈칸 (A)/(B)

- **출제 의도**: 긴 본문을 한 문장 요약문으로 압축, 핵심 어구 2곳 빈칸. 두 어구의 조합 추론.
- **표면 형태**:
  - question_text: "다음 글의 내용을 한 문장으로 요약하고자 한다. 빈칸 (A), (B)에 들어갈 말로 가장 적절한 것은?"
  - passage: 본문.
  - summary: `"... (A) ______ ... (B) ______ ..."` (시스템이 박스로 감쌈). 빈칸 정확히 2개, (A)/(B) 라벨 각 1번씩.
  - choices: 5개 (A)-(B) 단어 조합. 형식: `"(A) word1 …… (B) word2"`.
- **본문 마커**: `______` × 2 + `(A)` `(B)` 라벨. 레이아웃 `passage_segments`.
- **중요**: choices는 평탄 list[str]이지만 **실질적으로 2컬럼 매트릭스의 lossy 표현**이다. 본 프로젝트에서 §2.2 Gap B(매트릭스)와 직접 연결.
- **출처**: `app/llm/prompts.py:244-252`.

#### (23) `장문(41-42)` — 장문 세트 (제목 + 어휘)

- **출제 의도**: 긴 본문 1개 + 2문항 세트. 41=제목, 42=어휘(밑줄 (a)~(e) 5개 중 부적절).
- **표면 형태**:
  - passage: 본문 전체 (제목 + 본문). `(a)~(e)` 라벨 5개를 단어 직전에 평문으로 박음.
  - sub_questions: 1개 (42번 어휘).
    - choices: `["(a)","(b)","(c)","(d)","(e)"]`.
- **본문 마커**: `(a)~(e)` 라벨은 LLM 평문, `_word_` underline은 시스템 후처리 (`_apply_alpha_markers`). 레이아웃 `long_set`. exam-generator의 `TYPE_SLOT_COUNT["장문(41-42)"] = 2`.
- **검증 기준**:
  - 5개 단어 중 1개만 부적절 (어휘(30)와 동일한 검증).
  - 라벨 등장 순서: 본문 위→아래 (a)→(b)→(c)→(d)→(e) 알파벳 순.
- **출처**: `app/llm/prompts.py:253-271`.

#### (24) `장문독해(43-45)` — 장문 세트 (순서 + 지칭 + 일치)

- **출제 의도**: (A)~(D) 4단락 본문 + 3문항 (43=순서, 44=지칭, 45=일치).
- **표면 형태**:
  - passage = (A) 단락, sub_passages = `[[B], [C], [D]]`.
  - 본문 안 `(a)~(e)` 지칭 라벨 5개. 4:1 분포 강제 (4개는 주인공, 1개는 부수 인물).
  - referent_assignments: 5개 인물명 (`['Leo','Mr.Harrison','Leo','Leo','Leo']` 형식).
  - sub_questions: 2개 (44 지칭, 45 일치).
- **본문 마커**: `(a)~(e)` + `(A)~(D)` (시스템 후처리). 레이아웃 `long_set`. `TYPE_SLOT_COUNT = 3`.
- **도메인 위험 (audit-review-domain §4.4)**: 일치(45) 변형은 정답 유일성 + 5개 선택지 모두 본문에서 파생되어야 한다는 강한 제약. **LLM 자동 변형 시 오답 선지가 본문과 무관해질 위험 가장 높음**.
- **검증 기준**:
  - 4:1 분포 강제 (validator가 Counter로 자동 검증).
  - Y(부수 인물) 라벨 직후 단어는 **반드시 명시적 호칭** (대명사 he/she/him 금지).
  - 동성 X/Y 캐스팅 + 청자/주체 모호성 회피.
- **출처**: `app/llm/prompts.py:272-318`, `_shuffle_long_set_passages` (`generator.py:90-206`).

### 1.3 도메인 후처리 로직 (스키마와 분리)

exam-generator의 후처리는 스키마 책임이 아니라 어댑터 책임(audit §4.3 동의):

| 로직 | 위치 | 책임 |
|---|---|---|
| `_apply_alpha_markers` | `app/llm/generator.py:221-238` | (a)~(e) 라벨 직후 단어에 underline 자동 부착 |
| `_shuffle_long_set_passages` | `app/llm/generator.py:90-206` | 장문독해(43-45) 단락 셔플 + 정답 재계산 |
| `_attach_group_labels` | `app/llm/generator.py:474-512` | 동일 대분류 연속 출제 시 `[N~M]` 그룹 라벨 |
| `_expand_sub_questions` | `app/llm/generator.py:431-471` | sub_questions를 N개 Question으로 평탄화 |

본 프로젝트는 `packages/llm/normalizer.py` 또는 `packages/extractor/`에 위치 권고.

---

## 2. 자료 sweep으로 발견되는 sub-form

### 2.1 정의

**sub-form**: 같은 24개 type 안에서 **표면 형태 또는 표현 방식이 다르지만 출제 의도는 같은** 변형. 새 type을 만들지 않고 **기존 type 위에 부가 필드**로 표현.

CLAUDE.md v0.3 §6.2 원칙: "**새 type은 도입하지 않는다** — 기존 24개로 표현 불가능한 케이스가 발견되면 PM 결정."

### 2.2 Gap A — 본문 내장형 어휘/어법 선택 `(A) [opt1 / opt2]`

- **이름**: `inline_word_choice` (sub-form 식별자)
- **상위 type (확실)**:
  - **어법(29)** — 옵션이 **단어 활용형 변형** (예: `(A) [is / are]`, `(B) [doing / done]`, `(C) [which / where]`)
  - **어휘(30)** — 옵션이 **의미 변별 어휘쌍** (예: `(A) [embrace / reject]`, `(B) [rapid / slow]`)
- **상위 type (추정 — 와이프 인터뷰 대상)**:
  - 학교 내신에서 **어휘+어법 혼합형** 케이스 존재 — 두 type의 sub-form이 한 문제 안에 섞임. 이 경우는 §5.1 미해결 질문.
- **표면 형태**:
  - 본문 중간에 `(A) [opt1 / opt2]` 박스 2~3개 (3개가 표준, 2개도 등장).
  - question_text: "다음 글의 (A), (B), (C)의 각 네모 안에서 [어법에 맞는 표현 / 문맥에 맞는 낱말]로 가장 적절한 것은?"
  - 선택지 5개: `(A)col-(B)col-(C)col` 매트릭스 (Gap B와 직결).
  - 정답 1개 (5지선다 중 하나).
- **표현 방식 권고 (architect 결정 위임)**:
  ```
  Question:
    type: "어법(29)" 또는 "어휘(30)"   # 상위 type
    inline_choices: list[InlineChoice]?  # sub-form 활성 시
      - InlineChoice:
          label: str        # "(A)", "(B)", "(C)"
          options: list[str]   # 보통 2개, 어휘형은 3개도 가능
          answer_index: int    # 0-based
          position_marker: str  # 본문 내 위치 식별 (audit §4-4 ADR 의존)
          kind: Literal["vocabulary", "grammar", "mixed"]   # 박스별 의도
    choices: list[str]   # 5개 매트릭스 (평탄화) 또는 ChoiceMatrix
    answer: int   # 1~5
  ```
  - 부가 필드 활성 조건: `inline_choices is not None`이면 sub-form. 평가원 표준 `①_word_` 마커형은 `inline_choices is None` (기존 표현 유지).
  - `kind` 필드는 박스별로 다르게 설정 가능 — 어휘+어법 혼합형 표현용.
- **PM 권고와의 정합성 (D-1/D-2/D-3)**:
  - D-1: Passage 메타와 무관 (Question 레벨 sub-form).
  - D-2: Translation과 무관.
  - D-3: Workspace와 무관.
  - **충돌 없음**.
- **빈도 (audit-review-domain §3.1 추정)**:
  - 평가원/수능: ≈ 0%.
  - 학교 내신: 30~50% (특히 중3~고2).
  - 사설 변형문제집: 매우 흔함.
  - **와이프 사용 빈도: 높음 (추정)** — §5.1 인터뷰 대상.
- **검증 기준**:
  - 각 박스 옵션이 본문 문맥에서 하나만 자연스러워야 함 (정답 유일성).
  - 어휘형 박스는 dictionary 동의어 쌍 회피 (변별력 없음).
  - 어법형 박스는 회색지대 문법 회피 (예: 비제한적 관계사).
- **흔한 실패 모드**:
  - 두 옵션이 모두 문맥상 가능 (정답 모호).
  - 박스 위치가 본문 핵심 의미를 결정하지 않는 비-핵심 단어.

### 2.3 Gap B — 다중 선택지 매트릭스 (A/B/C 컬럼)

- **이름**: `choice_matrix`
- **관계**: **Gap A의 선택지 면**. Gap A를 표현 가능하게 만들면 Gap B는 자동으로 따라옴 (audit-review-domain §3.2 — "한 유형의 본문 면 / 선택지 면").
- **상위 type (확실)**:
  - **어법(29)**, **어휘(30)** — Gap A의 선택지 면.
  - **요약문(40)** — `(A) word1 …… (B) word2` 형태로 **이미 운영 중인 lossy 평탄화**. exam-generator는 평탄 `list[str]`로 다루지만 실질은 2컬럼 매트릭스.
- **상위 type (추정 — 와이프 인터뷰 대상)**:
  - **장문(41-42)의 42번** — (a)~(e) 5개 라벨 중 1개 부적절 형태. 매트릭스가 아니라 평탄 5지지만, 본문 내장형 변형 시 매트릭스로 변환 가능성 존재. §5.1 인터뷰 대상.
- **표면 형태**:
  - 컬럼 라벨: `(A)`, `(B)`, (`(C)`).
  - 행: 5개 (5지선다).
  - 각 행이 컬럼별 옵션 조합 (예: `① embrace … rapid … include`).
- **표현 방식 권고 (architect 결정 위임 — audit §4-8, domain-review §3.2)**:
  - **권고 1 (audit §3.1, ChoiceMatrix 별도)**:
    ```
    Question:
      choices: ChoiceMatrix?
        - columns: list[str]   # ["(A)", "(B)", "(C)"]
        - rows: list[list[str]]   # 각 행이 columns 길이만큼
    ```
  - **권고 2 (domain-review §3.2, choice_format 디스크리미네이터)**:
    ```
    Question:
      choices: list[str]   # 기본 평탄
      choice_format: Literal["flat", "matrix_AB", "matrix_ABC"]
      choice_columns: Optional[list[str]]   # 매트릭스일 때만
      choice_rows: Optional[list[list[str]]]   # 매트릭스일 때만
    ```
  - **domain 의견**: 권고 2 (디스크리미네이터)가 평가원 요약문(40) 평탄화 호환성·마이그레이션 부담 최소화 측면에서 우월. architect의 §5.5 의견 대기.
- **PM 권고와의 정합성**: 충돌 없음.
- **빈도 (audit-review-domain §3.2 추정)**: Gap A와 동일 (high).

### 2.4 Gap K — 마커/텍스트 분리 (audit §3.2 / §4-6)

엄밀히는 sub-form이 아니라 **모든 type에 영향을 주는 표현 정규화**. 본 §2에 등록한 이유: 분리 결정이 24개 type 전체의 표현 방식을 바꾸기 때문.

- **이름**: `marker_separated_body`
- **상위 type**: 마커를 사용하는 모든 유형 — 21, 29, 30, 31, 32, 33, 34, 35, 38, 39, 40, 41-42, 43-45 (총 13개).
- **현황 (exam-generator 방식)**: 마커가 본문 텍스트에 직접 박힘 (`_..._`, `①②③④⑤`, `______`, `(a)~(e)`).
- **본 프로젝트 권고 (audit §4-6, domain-review §3.5)**: 분리.
  - `Passage.body_text`: 마커 제거된 정제 영어 본문.
  - 마커는 별도 `Annotation` 또는 `Marker` 엔티티로 표현 (kind 분기).
- **PM 권고와의 정합성**: D-1/D-2/D-3 직접 충돌 없음. 단 D-1의 `body_text` 필드 정의가 "마커 분리 정책은 §4-6 ADR에서 결정"으로 미정 명시.
- **표현 방식 권고 (architect 결정 위임)**:
  - 마커와 SyntaxAnnotation을 데이터 모델에서 통합 vs 분리:
    - **통합 (domain-review §3.5 권고)**: `Annotation.kind`에 `marker_circled` / `marker_blank` / `marker_underline` / `syntax_top_label` / `syntax_bracket` 등 모두 들어감. 단순.
    - **분리**: `Marker` 별도 엔티티 + `SyntaxAnnotation` 별도. kind enum 비대화 회피.
  - **domain 입장**: 모델 통합 권고. 단 architect 결정 위임 (§5.6).
- **빈도**: 마커 사용 type 13개 모두 영향. **모든 type에 보편적**.

### 2.5 Gap I 보강 — 학년 수준 표시

audit-review-domain §4.2가 권고했고 PM이 D-1에서 채택 — `Passage.target_grade` enum 필수. **본 sub-form 카탈로그에는 "Passage 메타 차원" 보강이라 등재만**. 더 이상 재논의 필요 없음.

### 2.6 빠진 sub-form 가능성 (와이프 인터뷰 대상)

다음은 **추정**으로 등재만 하고 §5에 미해결 질문으로 등록:

- **단답형 영작 변형**: 학교 내신에서 빈번. exam-generator 5지선다 enum과 충돌하므로 새 type일 가능성. **추정** — §5.2.
- **부분 해석 빈칸**: 본문은 영어 그대로, 한 문장만 한국어 빈칸 (해석 채우기). 학교 내신 일부. **추정** — §5.2.
- **어구·문장 영영 풀이**: 어휘 변형의 한 갈래. **추정** — §5.2.

---

## 3. Phase 3 변형 생성에서의 variant_kind 후보

### 3.1 정의

**variant_kind**: 같은 type 안에서 **원본 → 변형의 변환 규칙**. `VariantQuestion.derived_from_question_id` + `variant_kind` 조합으로 표현.

CLAUDE.md v0.3 §6.2: "변형문제(VariantQuestion) — 같은 24개 type 안에서 원본의 `derived_from_question_id` + `variant_kind` 필드로 표현."

### 3.2 variant_kind 후보 목록

각 후보마다: **이름** / **적용 가능 type** / **변형 규칙** / **검증 기준**.

#### 3.2.0 V1~V10 요약 표 + VariantKind enum 정합

`shared/schemas/question.py` `VariantKind` enum 멤버 (v0.4, 2026-05-15) 와 1:1 정합:

| ID | variant_kind (enum value) | `VariantKind` enum 멤버 | 적용 type (enum value 후보) | 변형 입력 | 자산화 가치 | 우선순위 (§3.4) |
|---|---|---|---|---|---|---|
| V1 | `vocabulary_swap` | `VOCABULARY_SWAP` | `vocabulary_30`, `long_set_41_42` (42번) | 원본 Question 또는 Passage | 중 | 2순위 |
| V2 | `vocabulary_inline` | `VOCABULARY_INLINE` | `vocabulary_30`, `blank_phrase_31` | Passage | 높음 | **1순위** |
| V3 | `grammar_swap` | `GRAMMAR_SWAP` | `grammar_29` | 원본 Question 또는 Passage | 중 | 2순위 |
| V4 | `grammar_inline` | `GRAMMAR_INLINE` | `grammar_29` | Passage | 높음 | **1순위** |
| V5 | `blank_inference` | `BLANK_INFERENCE` | `blank_phrase_31`, `blank_clause_32~34` | Passage | 높음 | **1순위** |
| V6 | `topic_main_idea_swap` | `TOPIC_MAIN_IDEA_SWAP` | `main_idea_22`, `topic_23`, `title_24` | Passage | **최고** | **1순위** |
| V7 | `order_shuffle` | `ORDER_SHUFFLE` | `paragraph_order_36`, `paragraph_order_37` | Passage | 중 (1지문 1변형) | **1순위** |
| V8 | `sentence_insertion_shift` | `SENTENCE_INSERTION_SHIFT` | `sentence_insertion_38`, `_39` | Passage | 중 | 2순위 |
| V9 | `irrelevant_sentence_inject` | `IRRELEVANT_SENTENCE_INJECT` | `irrelevant_sentence_35` | Passage | 중 | 2순위 |
| V10 | `summary_blank_swap` | `SUMMARY_BLANK_SWAP` | `summary_40` | Passage | 중 | 2순위 |

**`ORIGINAL`** (`variant_kind = "original"`): 입력에서 추출된 원본 (변형 아님). 모든 24개 type 에 적용.

각 V의 상세는 아래 §3.2.1~§3.2.10.

**v0.3 → v0.4 enum 변경**:
- ❌ 폐기: `THEME_REWORD = "theme_reword"` (v0.3 잠정 명명 — 데이터 사용 0건).
- ✅ 신규 (V6 통합): `TOPIC_MAIN_IDEA_SWAP = "topic_main_idea_swap"` — V6 명세가 요지(22)/주제(23)/제목(24) 3개 type 을 포함하므로 enum 명도 일관 갱신.
- ✅ 신규 5개: `VOCABULARY_INLINE` (V2) / `GRAMMAR_INLINE` (V4) / `SENTENCE_INSERTION_SHIFT` (V8) / `IRRELEVANT_SENTENCE_INJECT` (V9) / `SUMMARY_BLANK_SWAP` (V10).


#### V1. `vocabulary_swap` — 어휘 교체

- **`VariantKind` enum**: `VOCABULARY_SWAP` (value: `"vocabulary_swap"`)
- **적용 type (확실)**: 어휘(30), 장문(41-42)의 42번.
- **변형 규칙**:
  1. 입력: 원본 Question (어휘(30) 또는 41-42), 또는 원본 Passage.
  2. 본문에서 5개(또는 (a)~(e)) 어휘 후보 위치 재선택 또는 유지.
  3. 5개 후보 중 1개를 의미 부적절한 단어로 swap.
  4. 출력: `Question(type=동일, variant_kind="vocabulary_swap", derived_from=원본id)`.
- **검증 기준**:
  - 부적절 단어가 본문 의미를 명확히 어긋나게 만들어야 함.
  - 4개 적절 단어가 dictionary 동의어로 swap 가능한 변별 가치 있는 위치.
  - 정답 유일성 (qa-validator 별도 LLM call).

#### V2. `vocabulary_inline` — 어휘 인라인화 (Gap A 어휘형 sub-form 변환)

- **`VariantKind` enum**: `VOCABULARY_INLINE` (value: `"vocabulary_inline"`) — **1순위**
- **적용 type (확실)**: 어휘(30), 빈칸-구(31).
- **변형 규칙**:
  1. 입력: 원본 Passage.
  2. 본문에서 핵심 어휘 2~3곳 위치 선택.
  3. 각 위치를 `(A) [opt1 / opt2]` 박스로 변환 (sub-form `inline_word_choice` 활성).
  4. 출력: `Question(type="어휘(30)", variant_kind="vocabulary_inline", inline_choices=[...], choices=[5개 매트릭스])`.
- **검증 기준**:
  - 각 박스 옵션 정답 유일성.
  - 오답 옵션이 dictionary 동의어 쌍 회피.

#### V3. `grammar_swap` — 어법 교체

- **`VariantKind` enum**: `GRAMMAR_SWAP` (value: `"grammar_swap"`)
- **적용 type (확실)**: 어법(29).
- **변형 규칙**:
  1. 입력: 원본 Question 또는 Passage.
  2. 5개 어법 후보 위치 재선택 또는 유지.
  3. 1개를 어법상 틀린 형태로 swap.
  4. 출력: `Question(type="어법(29)", variant_kind="grammar_swap", derived_from=원본id)`.
- **검증 기준**:
  - 5개 어법 포인트 다양성.
  - 회색지대 문법 회피 (정답 모호 위험).
  - 미국식/영국식 차이로 갈리는 케이스 회피.

#### V4. `grammar_inline` — 어법 인라인화 (Gap A 어법형 sub-form 변환)

- **`VariantKind` enum**: `GRAMMAR_INLINE` (value: `"grammar_inline"`) — **1순위**
- **적용 type (확실)**: 어법(29).
- **변형 규칙**: V2 (vocabulary_inline)와 동형, kind만 grammar.
- **검증 기준**: V2와 동형 + 어법 정답 결정성.

#### V5. `blank_inference` — 빈칸 추론 변형

- **`VariantKind` enum**: `BLANK_INFERENCE` (value: `"blank_inference"`) — **1순위**
- **적용 type (확실)**: 빈칸-구(31), 빈칸-절(32), 빈칸-절(33), 빈칸-절(34).
- **변형 규칙**:
  1. 입력: 원본 Passage.
  2. 본문에서 thesis 문장의 핵심 어구/절 위치 선택.
  3. 그 위치를 `______`로 비움.
  4. 5개 영어 표현 (명사구 또는 절) 생성, 1개 정답 / 4개 오답 (본문 표현 변형 + too-narrow/too-broad).
  5. 출력: `Question(type="빈칸-구(N)" 또는 "빈칸-절(N)", variant_kind="blank_inference")`.
- **추가 sub-type 가능성 (추정 — §5.2)**: **빈칸-문장** (빈칸이 문장 1개) — 평가원에는 별 분류 없음, 사설 변형에서 등장. 만약 채택되면 type 코드 결정 필요 (PM).
- **검증 기준**:
  - 빈칸 위치가 본문 thesis의 핵심.
  - 정답이 본문 다른 곳에 그대로 등장하지 않음 (literal repetition 회피).
  - 오답이 너무 무관하지 않음.

#### V6. `topic_main_idea_swap` — 주제·요지·제목 선택지 갱신

- **`VariantKind` enum**: `TOPIC_MAIN_IDEA_SWAP` (value: `"topic_main_idea_swap"`) — **1순위 / 자산화 가치 최고**
- **v0.4 변경 (2026-05-15)**: v0.3 의 잠정 enum `THEME_REWORD` 는 본 V6 으로 통합. V6 명세가 요지(22)/주제(23)/제목(24) 3개 type 을 묶기 때문에 enum 명도 통합. 데이터 사용 0건이라 breaking change 부담 없음.
- **적용 type (확실)**: 요지(22), 주제(23), 제목(24).
- **변형 규칙**:
  1. 입력: 원본 Passage.
  2. 본문은 그대로.
  3. 5개 선택지 새로 생성 (sub-type별 형식 — 한국어 단문 / 영어 명사구 / 영어 제목).
  4. 출력: `Question(type=동일, variant_kind="topic_main_idea_swap", choices=[5개])`.
- **자산화 가치**: **본 6개 후보 중 가장 높음** — 본문 변형 없이 선택지만 갱신. 한 지문에서 22/23/24를 모두 변형 생성 가능.
- **검증 기준**:
  - 정답이 본문 thesis 정확 일치.
  - sub-type별 형식 준수 (영어 명사구는 동사 시작 회피 등).
  - 오답 4개의 패턴 다양성 (too-narrow / too-broad / 결론 반대 / 무관 그럴듯).

#### V7. `order_shuffle` — 순서배열 변형

- **`VariantKind` enum**: `ORDER_SHUFFLE` (value: `"order_shuffle"`) — **1순위**
- **적용 type (확실)**: 순서배열(36), 순서배열(37).
- **변형 규칙**:
  1. 입력: 원본 Passage (단락 1개여도 가능 — LLM이 의미 분할).
  2. 도입 1단락 + (A)/(B)/(C) 3단락으로 분할.
  3. 5개 순서 조합 선택지 생성.
  4. 출력: `Question(type="순서배열(N)", variant_kind="order_shuffle")`.
- **자산화 가치**: 한 지문에서 1회 변형 가능 (재변형 시 분할 위치만 달라지지만 변별력 떨어짐).
- **검증 기준**:
  - 단락 분할이 의미 단위 (문장 중간 자르기 금지).
  - 응결 단서 충분 (접속사·대명사·정관사).
  - 단락 길이 균형.
  - 정답 분포 편향 회피 (exam-generator의 Hotfix 17-2 참조).

#### V8. `sentence_insertion_shift` — 문장삽입 위치 변형

- **`VariantKind` enum**: `SENTENCE_INSERTION_SHIFT` (value: `"sentence_insertion_shift"`)
- **적용 type (추정)**: 문장삽입(38), 문장삽입(39).
- **변형 규칙**:
  1. 입력: 원본 Passage.
  2. 본문에서 1문장 추출 → given_sentence로.
  3. 본문 안 ①~⑤ 위치 마커 5개 부착.
  4. 출력: `Question(type="문장삽입(N)", variant_kind="sentence_insertion_shift")`.
- **빈도 (추정)**: 변형문제집 2순위 (audit-review-domain §3.6 분류).
- **검증 기준**:
  - 추출 문장이 인접 문장과 응결 단서로 강하게 연결.
  - 다른 4개 위치에서 흐름 단절 (정답 유일성).

#### V9. `irrelevant_sentence_inject` — 무관문장 변형

- **`VariantKind` enum**: `IRRELEVANT_SENTENCE_INJECT` (value: `"irrelevant_sentence_inject"`)
- **적용 type (추정)**: 무관문장(35).
- **변형 규칙**:
  1. 입력: 원본 Passage (5문장 추정 또는 LLM 분할).
  2. 1문장을 본문 주제와 관련 있어 보이되 흐름에서 벗어난 문장으로 swap.
  3. ①~⑤ 마커 부착.
  4. 출력: `Question(type="무관문장(35)", variant_kind="irrelevant_sentence_inject")`.
- **검증 기준**:
  - 무관 문장이 본문과 관련 있어 보여야 (완전 무관은 너무 명백).
  - 4개 정상 문장 간 응결 단서 보존.

#### V10. `summary_blank_swap` — 요약문 빈칸 변형

- **`VariantKind` enum**: `SUMMARY_BLANK_SWAP` (value: `"summary_blank_swap"`)
- **적용 type (추정)**: 요약문(40).
- **변형 규칙**:
  1. 입력: 원본 Passage.
  2. 본문 한 문장 요약문 생성.
  3. 핵심 어구 2곳 빈칸 (A)/(B).
  4. 5개 (A)/(B) 단어 조합 생성.
  5. 출력: `Question(type="요약문(40)", variant_kind="summary_blank_swap")`.
- **빈도 (추정)**: 2순위 (audit-review-domain §3.6).
- **검증 기준**:
  - (A)/(B) 두 어구 모두 본문 핵심 압축.
  - 5개 조합 중 1개만 정답.

### 3.3 variant_kind와 type의 관계 정리

```
Question.type:           24개 QuestionType enum 중 하나 (확정)
Question.variant_kind:   VariantKind enum — ORIGINAL | V1~V10 (v0.4 모두 활성, 2026-05-15)
```

- `variant_kind=ORIGINAL`: 입력에서 추출된 원본 문제 (exam-generator 호환). `derived_from_question_id = None`.
- `variant_kind=V1~V10`: 변형. ADR-0017 Accepted — 단일 `Question` 테이블 + `derived_from_question_id` self-FK NOT NULL (model_validator 강제).

`Question.variant_metadata` (JSONB | NULL) — 변형만의 추가 메타 (예: `llm_candidate_words`, `generation_attempt`). 원본 행에서는 항상 None. Phase 3 첫 변형 생성 PR 에서 구조 확정 (ADR-0017 D2-c).

### 3.4 Phase 3 우선순위 (audit-review-domain §3.6 + 본 §3.2 통합)

**1순위 — Phase 3 진입 시 LLM 변형 프롬프트 작성 대상 (5개)**:

| 순서 | ID | `VariantKind` enum | 적용 type | 자산화 가치 | 비고 |
|---|---|---|---|---|---|
| 1 | V6 | `TOPIC_MAIN_IDEA_SWAP` | `main_idea_22` / `topic_23` / `title_24` | **최고** | 본문 유지, 선택지만 갱신. 한 지문에서 22/23/24 모두 변형 |
| 2 | V2 | `VOCABULARY_INLINE` | `vocabulary_30` / `blank_phrase_31` | 높음 | 학원 변형문제집 핵심 (Gap A 어휘형) |
| 3 | V4 | `GRAMMAR_INLINE` | `grammar_29` | 높음 | V2 와 동형 (kind 만 grammar) |
| 4 | V5 | `BLANK_INFERENCE` | `blank_phrase_31` / `blank_clause_32~34` | 높음 | 변형문제집 단골 |
| 5 | V7 | `ORDER_SHUFFLE` | `paragraph_order_36` / `_37` | 중 | 한 지문 → 한 변형 |

**시작 가이드 (Phase 3 진입 후 첫 PR)**:
1. **V6 우선** — 본문 변형 없음 + 선택지 5개만 LLM 생성 → 가장 단순 + 자산화 가치 최고.
2. V6 통과 후 V2/V4 (sub-form 변환) 진행 — `inline_choices` 필드 + 매트릭스 `choice_format` 활용.
3. V5 (`blank_inference`) 는 빈칸 위치 결정 + 5개 선택지 생성 — V6 패턴 + 본문 마커 부착.
4. V7 (`order_shuffle`) 은 마지막 — LLM 의 단락 분할 자체가 새 도메인.

**2순위 — Phase 3 후반 또는 별도 sprint**:

| 순서 | ID | `VariantKind` enum | 적용 type | 비고 |
|---|---|---|---|---|
| 6 | V1 | `VOCABULARY_SWAP` | `vocabulary_30` / `long_set_41_42` | 평가원 표준형 |
| 7 | V3 | `GRAMMAR_SWAP` | `grammar_29` | 평가원 표준형 |
| 8 | V8 | `SENTENCE_INSERTION_SHIFT` | `sentence_insertion_38` / `_39` | — |
| 9 | V9 | `IRRELEVANT_SENTENCE_INJECT` | `irrelevant_sentence_35` | — |
| 10 | V10 | `SUMMARY_BLANK_SWAP` | `summary_40` | — |

**우선순위는 §5.1 와이프 인터뷰로 최종 검증 필요** (audit-review-domain §5.1과 동일 항목).

### 3.5 LLM 변형 프롬프트 사전 가이드 (실제 프롬프트는 Phase 3 별 PR)

ADR-0013 (Phase 2 보강 파이프라인) 의 augment 패턴을 모태로 한 사전 가이드. 실제 프롬프트 본문은 Phase 3 진입 시 도메인 + LLM 코드 PR 에서 작성.

#### 3.5.1 공통 구조 (ADR-0013 augment 패턴 재사용)

`packages/llm/augment.py` 의 패턴을 그대로 답습:

1. **입력 schema** (Pydantic): `Passage` (또는 `Question`) — 원본.
2. **출력 schema** (Pydantic): `VariantOutput` — 1개 변형 후보 + `plan` (자기계획) + `naturalness_check` (자가검증).
3. **mode 파라미터** (ADR-0013 mode 패턴 확장):
   - `generate` (default): 새 변형 생성.
   - `retry_on_uniqueness_fail`: qa-validator 가 정답 유일성 실패 보고 → LLM 이 재생성.
   - `regenerate`: 사용자가 거부 → 같은 type/variant_kind 로 새 후보.
4. **LLM 자가검증** (exam-generator 흡수): `naturalness_check: Literal["OK", "REWRITE_SCOPE_TOO_BROAD", ...]` — 변형 결과의 자연스러움 자체 평가.

#### 3.5.2 V6 (`topic_main_idea_swap`) — 첫 변형 프롬프트의 모범 (1순위 #1)

```
입력: Passage (body_text + translation + vocabulary)
출력: VariantOutput:
  - type: Literal[main_idea_22, topic_23, title_24]   # 3개 중 LLM 선택 또는 호출자 지정
  - choices: list[str]  # 5개, type 별 형식 (한국어 단문 / 영어 명사구 / 영어 제목)
  - answer: int  # 1~5
  - explanation: str
  - plan: QuestionPlan
  - naturalness_check: Literal["OK", ...]

프롬프트 가이드:
  - 본문 thesis 정확히 1문장 식별 → 정답 선택지 압축.
  - 4개 오답 패턴 분포 강제: [too-narrow, too-broad, 결론 반대, 무관 그럴듯].
  - 영어 명사구 (topic_23) 의 경우 동사 시작 회피, 정관사 the 시작 권장.
  - 영어 제목 (title_24) 의 경우 4~10 단어, 첫 글자 대문자.
  - 한국어 단문 (main_idea_22) 의 경우 "~이다" 형식.

검증 포인트 (qa-validator §3.6):
  - 정답 유일성: 다른 4개 선택지 모두 변별 가능.
  - 형식 준수: type 별 형식 패턴 정합.
  - thesis 정합: 정답이 본문 thesis 와 의미 정확 일치 (LLM-as-judge 2차 호출 가능).
```

#### 3.5.3 V2/V4 (`vocabulary_inline` / `grammar_inline`) — Gap A sub-form 변환 (1순위 #2, #3)

```
입력: Passage
출력: VariantOutput:
  - type: vocabulary_30 (V2) 또는 grammar_29 (V4)
  - inline_choices: list[InlineChoice]  # 2~3개
      - label: "(A)" / "(B)" / "(C)"
      - options: list[str]  # 보통 2개
      - answer_index: int
      - position_marker: str  # 본문 내 위치
      - kind: vocabulary | grammar
  - choice_format: matrix_AB | matrix_ABC
  - choice_matrix: ChoiceMatrix  # 5행 매트릭스
  - answer: int

프롬프트 가이드:
  - 박스 2~3개 위치는 본문 핵심 어휘/어법 포인트.
  - 어휘형 옵션: dictionary 동의어 회피 (변별력 없음) — 반의어 또는 의미 충돌어.
  - 어법형 옵션: 회색지대 문법 회피 (비제한적 관계사 that/which 등).
  - 5행 매트릭스: 박스 N개 → 컬럼 N개 → 5행 = 박스별 옵션 조합.
  - 정답 = 모든 박스에서 자연스러운 조합 1개만.

검증 포인트:
  - 각 박스 정답 유일성 (qa-validator 박스별 검증).
  - 매트릭스 5행 모두 컬럼 길이 정합 (Pydantic validator 자동 강제).
```

#### 3.5.4 V5 (`blank_inference`) — 빈칸 추론 변형 (1순위 #4)

```
입력: Passage
출력: VariantOutput:
  - type: blank_phrase_31 (구) 또는 blank_clause_32~34 (절)
  - question_text: 표준 지시문
  - choices: list[str]  # 5개 영어 명사구 또는 절
  - answer: int
  - body_with_blank: str  # 본문에 `______` 1개 박힌 형태 (Annotation 으로 분리)

프롬프트 가이드:
  - 빈칸 위치: 본문 thesis 문장의 핵심 어구.
  - 연결어 처리: `that ______` 처럼 빈칸 직전 연결어가 있으면 choices 에 그 연결어 포함 금지.
  - 정답이 본문 다른 곳에 그대로 등장 금지 (literal repetition — 추론이 아니라 검색).
  - 오답 4개 패턴: 본문 표현 변형 + too-narrow + too-broad + 본문 일부 의미적 관련되되 빈칸 위치 부적합.

검증 포인트:
  - 정답 유일성.
  - literal repetition 자동 검출 (qa-validator).
```

#### 3.5.5 V7 (`order_shuffle`) — 순서배열 변형 (1순위 #5)

```
입력: Passage
출력: VariantOutput:
  - type: paragraph_order_36 또는 _37
  - given_passage: str  # 주어진 글 1단락
  - sub_passages: list[list[str]]  # [[A단락], [B단락], [C단락]]
  - choices: list[str]  # 정확히 ["(A)-(C)-(B)", "(B)-(A)-(C)", "(B)-(C)-(A)", "(C)-(A)-(B)", "(C)-(B)-(A)"]
  - answer: int

프롬프트 가이드:
  - 단락 분할: 의미 단위 (문장 중간 자르기 금지).
  - 응결 단서 충분: 각 단락 시작/끝에 다음 단락 가리키는 접속사/대명사/정관사.
  - 단락 길이 균형 (학생이 길이 추측으로 못 풀게).
  - 정답 분포 편향 회피 (5개 후보 균등 분포 — exam-generator Hotfix 17-2 참조).

검증 포인트:
  - 응결 단서 ≥ 2개 per 인접 단락 쌍.
  - 분할 위치가 문장 경계 (sentence boundary).
  - 정답 분포 통계 모니터링 (qa-validator history).
```

#### 3.5.6 후속 작업 (별 PR, 본 카탈로그 외)

- `docs/prompts/variant_v6_topic_main_idea_swap.md` 등 V1~V10 모두 별 마크다운 + few-shot 2~3개.
- `packages/llm/variant.py` — augment.py 와 대칭 구조 (mode 분기 + Pydantic 입출력).
- `POST /passages/{id}/variants` 라우트 (variant_kind 파라미터).

### 3.6 qa-validator 검증 시나리오 (ADR-0017 D3-c 하이브리드)

ADR-0017 D3-c 결정: `Question.uniqueness_validated: bool` (최신 상태 캐시) + 별도 `qa_validation_results` 테이블 (history). qa-validator agent 가 별 LLM call 로 검증.

#### 3.6.1 공통 검증 흐름

1. **입력**: 1개 `Question` (variant_kind != ORIGINAL).
2. **검증 LLM call**: 변형 생성 LLM 과 *다른 모델* 또는 *다른 프롬프트* — 자기검증 회피 (NRTW: LLM-as-judge 패턴).
3. **출력**: `QAValidationResult`:
   - `passed: bool`
   - `category: Literal["uniqueness", "naturalness", "format", "literal_repetition"]`
   - `note: str` (실패 사유)
   - `timestamp: datetime`
4. **저장**:
   - `Question.uniqueness_validated` ← 최신 결과의 `passed` 값.
   - `Question.uniqueness_validator_note` ← 최신 `note`.
   - `qa_validation_results` 테이블에 raw history append (별 PR — Phase 3).

#### 3.6.2 variant_kind 별 검증 카테고리 매핑

| variant_kind | 검증 카테고리 (우선순위) | 검증 방법 |
|---|---|---|
| `VOCABULARY_SWAP` / `VOCABULARY_INLINE` | (1) uniqueness (2) literal_repetition (3) format | LLM 2차 호출 + 본문 fuzzy match |
| `GRAMMAR_SWAP` / `GRAMMAR_INLINE` | (1) uniqueness (2) naturalness (회색지대 회피) | LLM 2차 호출 + 문법 규칙 체크리스트 |
| `BLANK_INFERENCE` | (1) uniqueness (2) literal_repetition | LLM 2차 호출 + 본문 fuzzy match (정답이 본문 어디 그대로 등장하는지) |
| `TOPIC_MAIN_IDEA_SWAP` | (1) thesis 정합 (2) format (3) uniqueness | LLM 2차 호출 (정답 ↔ thesis 의미 정합) + 형식 정규식 |
| `ORDER_SHUFFLE` | (1) 응결 단서 (2) 분포 편향 (3) uniqueness | LLM 2차 호출 (인접 단락 응결 분석) + 분포 통계 history |
| `SENTENCE_INSERTION_SHIFT` | (1) uniqueness (2) 응결 단서 | LLM 2차 호출 |
| `IRRELEVANT_SENTENCE_INJECT` | (1) 본문 주제 관련성 (2) uniqueness | LLM 2차 호출 |
| `SUMMARY_BLANK_SWAP` | (1) uniqueness (2) 본문 압축 정합 | LLM 2차 호출 |

#### 3.6.3 실패 시 흐름

```
variant 생성 → qa-validator 검증 → passed=False?
  ├─ Yes: retry (mode="retry_on_uniqueness_fail") — 최대 3회
  ├─ No: 사용자에게 노출 + uniqueness_validated=True 캐시
  └─ 3회 retry 모두 실패: 사용자에게 "검증 미통과" 라벨로 노출, 사용자 검수로 위임
```

CLAUDE.md §1.3 핵심 가치 명제 #3 ("편집 가능한 출력") 정합 — 자동 검증 실패도 사용자가 검수 후 채택할 수 있음.

#### 3.6.4 Phase 3 진입 시 qa-validator 활성화

CLAUDE.md §7.6 ("Phase 3 시작 시 활성화") 정합. Phase 3 첫 변형 생성 PR 과 동시 또는 직후 별 PR.

---

## 4. Annotation kind 카탈로그 (구문분석 도메인)

본 §은 Phase 1 영역 (`SyntaxAnnotation`). 영상 레퍼런스(`docs/reference-program-analysis.md`)의 6종 annotation을 도메인 관점에서 다듬는다. 본 카탈로그에 두는 이유: 한 자리에서 도메인 지식 통합.

### 4.1 6종 annotation 도메인 매핑

영상 레퍼런스 §2의 6종을 한국 영어 시험 출제·강의 도메인 관행과 매핑.

#### A1. `top_label` — 상단 라벨

- **시각**: 본문 위에 작은 글씨 + 색상 박스. 자유 문자열.
- **출제·교육적 의도**: 구/절의 **카테고리 명명**. 학생이 본문 위의 라벨만 보고 그 구간이 어떤 문법 단위인지 즉시 인지.
- **한국 출제 관행 흔한 사용 예**:
  - `=동명사주어`, `=to부정사(형)`, `(부사구)`, `(부사절)`, `(관계절)`, `(현재분사구문)`, `(전치사구)`, `(명사절)`.
  - `=` 접두는 그 단어가 직전 단어 또는 행동의 동의어/부연임을 표시 (영상 scene_006).
  - `(...)`는 구·절 라벨임을 표시.
- **카테고리 매핑 (영상 §3.3 하단 분석표)**: `phrase`, `clause`, `note` 중 하나.
- **검증/품질 기준**: 라벨 텍스트가 자유 문자열이라 사용자 선호 표기 다양 (예: `S` vs `주어` vs `Subject`). v0.1은 자유 문자열, v0.2+ preset 권고.

#### A2. `bottom_label` — 하단 라벨

- **시각**: 본문 아래 한 글자 약어.
- **출제·교육적 의도**: 문장의 **5형식 주성분 표시**. S(주어) / V(동사) / O(목적어) / C 또는 OC/SC(보어). 한국 영어 강의에서 가장 보편적인 구문분석 표기.
- **한국 출제 관행 흔한 사용 예**:
  - `S`, `V`, `O`, `OC`, `SC`, `IO`(간접목적어), `DO`(직접목적어).
  - 보조 표기: `V'`(원형동사), `to-V`(to부정사 동사), `V-ing`(동명사·분사).
- **카테고리 매핑**: `sentence_role`.
- **검증/품질 기준**: 단일 토큰 또는 짧은 phrase 단위. 한 토큰에 라벨 2개 이상 겹치는 케이스 (예: `it`이 형식 주어 + 진주어 가리킴) — 시각 처리는 frontend-dev 책임 (CLAUDE.md §11).

#### A3. `highlight` — 형광펜 (배경색)

- **시각**: 단어/구의 배경색 (12색 팔레트 중 1색).
- **출제·교육적 의도**: **색상으로 카테고리 그룹핑**. 같은 색의 단어들이 같은 역할(예: 주어 그룹은 분홍, 동사 그룹은 파랑).
- **한국 출제 관행**:
  - 색상 컨벤션은 강사마다 다름 (영상 §5.1 미해결).
  - 와이프 인터뷰 필요 — 그녀의 색상 컨벤션이 있는지.
- **카테고리 매핑**: `note` (기본). 강사가 색상-카테고리 매핑을 정의하면 그에 따라 자동 분류 가능.
- **검증/품질 기준**: 색상 일관성 (같은 역할의 단어들이 같은 색).

#### A4. `bracket` — 괄호

- **시각**: `()`, `{}`, `[]` 다양한 괄호.
- **출제·교육적 의도**: **구·절의 범위 표시**. 한 절이 어디부터 어디까지인지 명확히 묶음. 중첩 절 분석에 필수.
- **한국 출제 관행**:
  - `()` — 일반 구.
  - `{}` — 명사절 또는 종속절.
  - `[]` — 관계절 또는 강조.
  - 컨벤션은 강사마다 다름 (와이프 인터뷰 §5.1).
- **카테고리 매핑**: `phrase` 또는 `clause`. 보통 top_label과 페어링 (`=관계절` 라벨 + `[]` 괄호).
- **검증/품질 기준**: 괄호 짝 맞음 (`(`마다 `)`). 중첩 시 시각적 가독성.

#### A5. `arrow` — 화살표 / 연결

- **시각**: 가는 줄로 두 토큰 연결. 곡선 가능.
- **출제·교육적 의도**: **단어 간 의미 관계 표시**.
  - 수식 관계: 형용사절 → 명사 (관계대명사가 가리키는 선행사).
  - 호응 관계: 주어 → 동사 (수일치 강조).
  - 동의어 관계: 본문 단어 → 다른 단어 (`each → every` 영상 예시).
  - 지칭 관계: 대명사 → 선행어.
- **한국 출제 관행 흔한 사용 예**:
  - 관계대명사 / 관계부사 → 선행사.
  - 동사 → 주어 (수일치).
  - 대명사 → 선행어 (장문독해 (a)~(e) 지칭과 유사).
- **카테고리 매핑**: `other` 또는 `note`. 영상 §3.3 표는 `(단위) each→every`처럼 `기타`로 분류.
- **검증/품질 기준**: 두 span 간 명확한 관계 명시. 화살표 방향 (from → to)이 의미상 옳음.
- **데이터 모델 권고 (영상 §4.3 동의)**: `arrow_target_span` 필드 — 화살표는 (start_span, end_span) 2개 span 필요.

#### A6. `inline_note` — 인라인 주석

- **시각**: 본문 위에 작게 떠 있는 텍스트 (라벨 형식 아님).
- **출제·교육적 의도**: **어휘 동의어/풀이 노출**. 학생이 단어를 보면서 동시에 동의어·풀이 즉시 학습.
- **한국 출제 관행 흔한 사용 예**:
  - `=foster, promote, increase, enhance` (영상 scene_006의 `develop` 위).
  - `cf. ~ 와 비교` (참고 표기).
  - 한국어 풀이 (`develop = 발전시키다`).
- **카테고리 매핑**: `note`. 영상 §3.3 표의 `주석` 행.
- **검증/품질 기준**: 자유 텍스트 — 검증 어려움. 사용자 책임.

#### A7. `underline` — 밑줄 (CLAUDE.md §2.1 명세이지만 영상 미관찰)

- **상태**: **확실하지 않음** — 영상 레퍼런스에 보이지 않음. CLAUDE.md Phase 1 DoD에는 명시.
- **출제·교육적 의도 (추정)**:
  - 핵심 표현 강조 (highlight와 다름 — highlight는 배경색, underline은 텍스트 밑선).
  - 해석 시 강조 단위 지정.
- **한국 출제 관행 (추정)**: highlight와 중복되는 경우 많음. 와이프 인터뷰 §5.4 등록.
- **카테고리 매핑 (추정)**: `note`.
- **검증/품질 기준**: highlight와 사용 분기 — 와이프 컨벤션 확인 필요.

### 4.2 6종 + 1 (underline) annotation kind enum 권고

영상 §4.3 권고와 정합. architect 작업 #5에 반영 권고:

```python
# SyntaxAnnotation.kind enum 후보 (도메인 관점)
Literal[
    "top_label",      # A1 — 상단 라벨 (자유 문자열)
    "bottom_label",   # A2 — 하단 라벨 (S/V/O/OC/SC)
    "highlight",      # A3 — 형광펜 (배경색, 12색 팔레트)
    "bracket",        # A4 — 괄호 () {} []
    "arrow",          # A5 — 단어 간 연결 (from_span, to_span)
    "inline_note",    # A6 — 인라인 주석 (어휘 동의어)
    "underline",      # A7 — 밑줄 (영상 미관찰, 와이프 확인 필요)
]
```

### 4.3 category 필드 (하단 분석표 행 매핑)

영상 §3.3 하단 분석표는 5개 카테고리로 자동 누적:

```python
Literal[
    "note",           # 주석 (highlight, inline_note 위주)
    "sentence_role",  # 주성분 (bottom_label 위주)
    "phrase",         # 구 (top_label + bracket의 구 단위)
    "clause",         # 절 (top_label + bracket의 절 단위)
    "other",          # 기타 (arrow의 동의어 표시 등)
]
```

`category`는 자동 결정이 가능한가? — 영상 §3.2 추정에서 "시스템이 자동 분류하거나 사용자가 행을 선택"으로 불명. **와이프 인터뷰 §5.4 등록**.

### 4.4 PM 권고와의 정합성

D-1/D-2/D-3 모두 SyntaxAnnotation과 무관 (Passage 메타 / Translation / Workspace 차원). 충돌 없음.

---

## 5. 미해결 / 추가 조사 필요

### 5.1 [PM + 와이프] 변형 유형 사용 빈도 / Gap A 어휘+어법 혼합형

audit-review-domain §5.1 + 본 §3.4 우선순위 검증.

**질문**:
1. 와이프가 학원에서 실제로 다루는 변형문제 유형 중 §3.4의 1순위 5개(V2/V4/V5/V6/V7) 사용 빈도는?
2. Gap A 본문 내장형에서 **어휘+어법 혼합형** (한 지문에 어휘 박스 + 어법 박스가 같이 박힌 형태) 케이스가 실제로 있는가? 있다면 빈도?
3. Gap B 매트릭스에서 **장문(41-42)의 42번이 매트릭스로 변형되는** 케이스 실존?
4. §3.2의 V1~V10 중 빠진 변형 유형이 있는가?

**기한**: Phase 3 진입 전. v0.1 스키마 작업 #5는 본 질문에 의존하지 않음.

**담당**: PM이 와이프 인터뷰 후 v0.3 변형 카탈로그 갱신.

### 5.2 [PM + 와이프] 빠진 sub-form / 신규 type 가능성

§2.6에서 추정으로 등재한 케이스 검증.

**질문**:
1. **단답형 영작 변형** — 학교 내신에서 "다음 빈칸에 알맞은 영어 단어/구를 쓰시오" 형태. 5지선다가 아니라 단답. **24개 type으로 표현 불가능 — 새 type 후보**. 와이프 사용 빈도?
2. **부분 해석 빈칸** — 본문 영어, 한 문장 한국어 빈칸. 사용 빈도?
3. **어구·문장 영영 풀이** — 어휘 변형의 한 갈래. 사용 빈도?
4. **빈칸-문장** sub-type — V5의 sub-type 후보 (평가원 별 분류 없음). 와이프 사용 빈도?

**기한**: Phase 3 진입 전.

**담당**: PM이 와이프 인터뷰. 새 type 도입 결정은 PM 단독 결정 (CLAUDE.md §6.2 — "기존 24개로 표현 불가능한 케이스가 발견되면 PM 결정").

### 5.3 [architect] choice_format 디스크리미네이터 채택 여부 (Gap B)

audit-review-domain §5.5와 동일.

**질문**: 본 §2.3의 **권고 2 (디스크리미네이터)** 채택 vs **권고 1 (ChoiceMatrix 별도 모델)** 채택? domain은 권고 2 선호.

**기한**: 작업 #5 진행 중.

**담당**: architect 결정. domain은 의견 제시 완료.

### 5.4 [PM + 와이프] SyntaxAnnotation 종류 sample 자료

audit-review-domain §5.4 + 영상 §5.1, §5.2, §5.3, §5.4와 동일.

**질문**:
1. 와이프의 실제 구문분석 자료 sample 1~3건 (이미지/HWPX).
2. 영상 §2의 6종 (top_label/bottom_label/highlight/bracket/arrow/inline_note) 외 사용 표기 있는가?
3. **A7 underline의 실제 사용 여부** (영상 미관찰, CLAUDE.md 명세).
4. 12색 팔레트의 색상 컨벤션 (강사별 vs 표준).
5. 라벨 텍스트 preset 메뉴 사용 여부.
6. 같은 span에 라벨 2개 이상 겹치는 케이스 빈도와 표기 규약.
7. 영상 §3.3 하단 분석표의 category 자동 분류 로직 (강사 입력 시 시스템이 자동 분류 vs 강사가 선택).

**기한**: Phase 1 진입 전.

**담당**: PM이 와이프 인터뷰. domain-expert가 결과를 v0.3 카탈로그에 흡수.

### 5.5 [architect] Annotation span 식별 방식 — token id vs character offset

audit-review-domain §5.2 + 영상 §4.1과 동일. **반복 강조** — 본 결정은 §4 Annotation kind enum의 모든 entries에 영향.

**질문**: domain-review §3.4의 **token id 1순위 검토** + 영상의 **단어 단위 선택** 추가 근거를 ADR에서 충분히 비교?

**기한**: Phase 1 진입 전 ADR.

**담당**: architect + frontend-dev + domain-expert 3자 합의.

### 5.6 [architect] 마커 / SyntaxAnnotation 통합 vs 분리 (Gap K)

audit-review-domain §5.6와 동일.

**질문**: 마커(출제용 표기)와 SyntaxAnnotation(구문분석 표기)을 데이터 모델에서 통합 vs 분리?

**기한**: Phase 1 진입 전 ADR.

**담당**: architect 결정. domain은 통합 권고.

### 5.7 [PM] Phase 3 정답 유일성 검증 메타 — Question에 자리 만들기

audit-review-domain §4.1 + 본 §3.2 V1~V10 모두에 영향.

**질문**: `Question.uniqueness_validated: bool` + `Question.uniqueness_validator_note: Optional[str]` v0.1 스키마에 자리 만들 것인가?

**기한**: 작업 #5 진행 중.

**담당**: architect + PM. domain은 권고.

### 5.8 [domain-expert 자체] 후속 산출물

본 카탈로그 v0.4 가 트리거하는 domain-expert 자체 후속 작업:

- `docs/prompts/variant_*.md` — V6/V2/V4/V5/V7 (1순위 5개) LLM 프롬프트 본문 + few-shot 예시. **Phase 3 진입 시점**. §3.5 사전 가이드를 모태로 작성.
- 와이프 인터뷰 후 v0.5 카탈로그 — §5.1, §5.2, §5.4 답변 흡수.
- 자료 sweep 추가 — 아잉카·내신 sample을 받으면 §2 sub-form 추가.
- annotation kind 카탈로그 v0.2 — 와이프 sample 받은 후 §4 보강.
- qa-validator 활성화 sprint (Phase 3) — §3.6 검증 카테고리를 자동 알고리즘으로.

---

## 6. 핸드오프 메모

### 6.1 → architect (작업 #5)

본 카탈로그가 작업 #5 입력으로 들어간다. 우선순위:

1. **§1.1의 24개 type enum**을 `Question.type` Pydantic enum으로 흡수. exam-generator 코드와 1:1 호환.
2. **§2의 sub-form**을 `Question`의 부가 필드로 표현 (`inline_choices`, `choice_format` 디스크리미네이터). §5.3 결정 후 확정.
3. **§3의 variant_kind**를 `Question.variant_kind` enum 자리로 두되 v0.1은 `"original"`만 활성. V1~V10은 Phase 3 진입 전 enum 추가.
4. **§4의 SyntaxAnnotation kind enum 7종**을 `shared/schemas/annotation.py`에 흡수. span 식별 방식은 §5.5 ADR로 미룸.
5. **§5의 미해결 항목** 중 §5.3, §5.5, §5.6, §5.7은 architect 결정. 본 카탈로그가 의견·근거 제시 완료.

### 6.2 → PM (Dennis)

§5.1, §5.2, §5.4의 와이프 인터뷰 일정. 우선순위:

1. **Phase 1 진입 전**: §5.4 (SyntaxAnnotation sample) — Phase 1 핵심 산출물 차단 해제.
2. **Phase 3 진입 전**: §5.1, §5.2 (변형 유형 빈도, 신규 type 가능성).

### 6.3 → 다른 agent

- **frontend-dev**: §4.2 annotation kind enum + 영상 §4.4 단축키 명세를 Tiptap PoC 다음 단계 입력으로.
- **qa-validator**: §3.2 V1~V10 각 검증 기준을 Phase 3 진입 시 자동 검증 알고리즘으로 변환. §5.7 메타 필드 영속화 패턴.

---

## 7. 변경 이력

| 버전 | 날짜 | 변경 |
|---|---|---|
| v0.1 | 2026-05-02 | 초안 — 5개 변형 유형을 별 카테고리로 정의 (잘못된 전제, 폐기) |
| v0.2 | 2026-05-02 | 전면 재작성 — 24개 유형 인벤토리 + sub-form (Gap A/B/K) + variant_kind 10개 + annotation kind 7종 + 미해결 8개. CLAUDE.md v0.3 §6.2 정정 반영. |
| v0.3 | 2026-05-02 | 각 24개 type 에 snake_case 영문 enum value 후보 컬럼 추가. |
| v0.4 | 2026-05-15 | ADR-0017 Accepted 후속 — V1~V10 모두 `VariantKind` enum value 명시 (`shared/schemas/question.py` 동시 보강). V6 명 변경 `THEME_REWORD` → `TOPIC_MAIN_IDEA_SWAP`. §3.4 1순위 표 상세화. §3.5 LLM 프롬프트 사전 가이드 신규. §3.6 qa-validator 검증 시나리오 신규. |
| v0.3 | 2026-05-02 | (1) §1.1 24개 유형 표에 **enum value 후보 (snake_case 영문)** 컬럼 추가 — `Question.type` Pydantic enum의 1차 source. (2) §1.1에 LAYOUT_PATTERN 컬럼 추가. (3) enum value 명명 컨벤션 명시 (architect 검토 권고). (4) §3.2.0 V1~V10 요약 표 추가 — 적용 type을 enum value 후보로 매핑. PM 명세 (24개 type code 추출 + 매핑 표) 반영. |
