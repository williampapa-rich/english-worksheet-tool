"""라벨 수평 align 보정 — P1-8b fix 라운드.

라벨 단락은 본문과 별도 단락이라, 본문 단어 위/아래 정렬을 위해 leading whitespace
개수를 산출해야 한다.

설계 변경 이력:
    - 1차 (pillow 폰트 metric 실측): TNR 폰트 폭으로 본문 prefix 폭 → 라벨 폰트
      좌표계 공백 수 환산. PM 검수 결과 한컴이 본문 paraPr LEFT 임에도 spacing 을
      페이지 폭에 맞춰 늘려 ("The   quick   (brown)   ...") 폰트 metric 환산이
      어긋남 — "동격" 이 본문보다 훨씬 오른쪽으로 가버림.
    - 2차 (현재, 글자 수 비례): 본문도 라벨도 같은 한컴 spacing 룰을 따른다고 가정.
      anchor 글자 수에 비례한 컬럼 위치로 단순화.
      라벨 leading 공백을 본문 charPr (id=0, plain 10pt) 로 출력해 폰트 폭 일치
      → leading 개수 = anchor 글자 수 (1:1).

본 모듈은 호환성을 위해 ``label_leading_spaces`` 동일 시그니처 유지. 내부 구현만
글자 수 비례로 교체.
"""

from __future__ import annotations


def label_leading_spaces(body_prefix: str) -> int:
    """라벨이 본문 ``body_prefix`` 끝 위치 위에 정렬되도록 라벨 단락에 채울 공백 수 산출.

    글자 수 비례 (1:1) 방식 — 라벨 leading 공백은 호출자가 본문과 동일 charPr
    (body 10pt) 로 출력해 폰트 폭이 일치한다. 따라서 anchor 글자 수가 곧 컬럼 수.

    한컴이 본문 paraPr LEFT 임에도 spacing 을 페이지 폭에 맞춰 늘리는 동작을
    pillow 폰트 metric 으로 환산할 수 없어, 같은 한컴 spacing 룰 위에 비례 관계로
    추정하는 것이 더 안정적이다 (PM 검수 1차 결과 반영).
    """
    return len(body_prefix)
