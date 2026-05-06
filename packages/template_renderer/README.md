# `packages/template_renderer`

Worksheet HTML 템플릿 + (예정) Jinja2 렌더 + Playwright PDF 변환 파이프라인.

- **상태**: Stage 0 — 자산 도입만 완료. 렌더/변환 코드는 Stage 2 (Phase 1 baseline 후)
  에 추가.
- **출처**: 외부 작업자가 작성한 워크시트 템플릿 3종 (2026-05-06 도입).
- **관련 문서**:
  - `docs/template-rendering-analysis.md` (도입 분석 + PM 결정 5건)
  - `docs/adr/0008-phase-1-output-format.md` (HWPX → HTML/PDF 전환)
  - annotation split-mark 렌더링 ADR (향후 ADR — 번호 확정 시 갱신)
  - 향후 ADR-0011 (Worksheet HTML 템플릿 + Playwright PDF 파이프라인) — Stage 1 진입 시
    승격

## 디렉토리

```
packages/template_renderer/
├── README.md                  # 이 파일
└── templates/
    ├── classic.html           # Style 1 — 수능 모의고사 톤 (보관, MVP 미노출)
    ├── modern.html            # Style 2 — 모던 미니멀 (보관, MVP 미노출)
    └── playful.html           # Style 3 — 친근한 학원 핸드아웃 (★ MVP 채택)
```

**MVP 노출 정책**: PM 결정 (2026-05-06) — `playful` 1종만 라우트 노출. classic / modern
은 보관 — Phase 2 종료 후 와이프 피드백에 따라 추가 노출 검토.

## 데이터 계약

세 템플릿 모두 동일한 데이터 모델을 받는다. 사용자는 스타일만 바꿔서 렌더링.

```python
{
    "academy": {
        "name": str,             # 학원명 (예: "윌리엄 영어학원")
        "theme_color": str,      # CSS hex (예: "#2563eb"). 미지정 시 기본 파란색
        "logo_url": str | None,  # 로고 이미지 URL. None 이면 텍스트/아이콘 폴백
    },
    "worksheet": {
        "title": str,            # 워크시트 제목
        "subtitle": str | None,  # 부제 (예: "Week 04")
        "page_number": int,      # 현재 페이지
        "total_pages": int,      # 전체 페이지 수
        "orientation": str,      # "portrait" | "landscape"
    },
    "student": {                 # ⚠ schema 미도입 — 렌더 시점 빈칸 출력만 (PM 결정 #5)
        "name": "",
        "class_name": "",
        "date": "",
    },
    "instruction": str | None,
    "questions": [
        {
            "number": int,
            "label": str | None,
            "content_html": str, # annotation split-mark 렌더러 산출 HTML 주입 (ADR 번호 확정 후 갱신)
        },
        ...
    ],
}
```

`content_html` 은 `| safe` 필터로 이스케이프 없이 주입된다. 신뢰 가능한 소스 (직접
렌더링한 결과) 만 넣을 것 — 사용자 직접 HTML 입력 경로가 생기면 sanitizer 필요.

## `shared/schemas` 매핑 (Stage 1 작업)

현재 `shared/schemas/worksheet.py` 와의 갭 4건 — Stage 1 (Phase 1 baseline 후) 에
schema 마이그레이션 + 어댑터로 해소.

| 템플릿 변수 | 현재 schema | Stage 1 작업 |
|---|---|---|
| `academy.name` | ❌ | Tenant / Workspace 레벨 필드 추가 |
| `academy.theme_color` | `Branding.primary_color` | 어댑터 매핑만 |
| `academy.logo_url` | `Branding.logo_url` | ✅ 그대로 |
| `worksheet.title` | `Worksheet.title` | ✅ |
| `worksheet.subtitle` | ❌ | 신규 필드 |
| `worksheet.orientation` | ❌ | 신규 필드 |
| `instruction` | ❌ | 신규 필드 |
| `questions[].label` | ❌ | `WorksheetItem.label` 신규 |
| `student.*` | ❌ | **도입 안 함** (PM 결정 #5) |

## PDF 렌더 (Stage 2 — 미구현)

Playwright (headless Chromium) 채택 (PM 결정 #2). Stage 2 시작 시 `pyproject.toml` +
렌더 함수 추가.

```python
from playwright.async_api import async_playwright

async def render_pdf(html: str, output_path: str, landscape: bool = False) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.pdf(
            path=output_path,
            format="A4",
            landscape=landscape,
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        await browser.close()
```

**주의**:
- `@page size` 와 `landscape` 파라미터가 일치해야 함 (둘 다 `worksheet.orientation`
  한 값에서 파생).
- `print_background=True` 가 빠지면 playful 의 컬러 배너가 PDF 에서 사라짐.
- `margin` 모두 0 — `.page` 요소가 자체 패딩 (20mm) 을 가지므로 이중 들여쓰기 회피.

## 폰트 / CDN 정책 (PM 결정 #3)

CDN 유지 (사용자 환경이 일반 인터넷). 자가 호스팅 필요 시 폰트 파일을
`packages/template_renderer/static/fonts/` 에 두고 `@font-face` 로컬 경로 참조하도록
템플릿 수정.

| 폰트 | 소스 | 용도 |
|---|---|---|
| Pretendard | jsDelivr (orioncactus) | 모든 스타일 산세리프 본문 |
| Noto Serif KR | Google Fonts | classic 본문 |
| Fraunces | Google Fonts | modern 디스플레이 |
| Tabler Icons | jsDelivr | playful 배지 아이콘 |

## 템플릿 커스터마이징 포인트

각 템플릿 `:root` CSS 변수로 디자인 토큰 노출. `academy.theme_color` 가 인라인
스타일로 `--theme` 에 주입됨.

| 변수 | 용도 | 적용 |
|---|---|---|
| `--theme` | 메인 컬러 (배너/강조선/번호) | 모든 스타일 |
| `--ink` | 본문 텍스트 컬러 | 모든 스타일 |
| `--muted` | 보조 텍스트 (라벨, 부제) | 모든 스타일 |
| `--surface` | 질문 카드 배경 | playful |
| `--line` | 구분선 컬러 | 모든 스타일 |

playful 의 `--theme-soft` / `--theme-mid` 는 `color-mix(in srgb, ...)` 로 자동 생성 —
Chromium 111+ 필요. WeasyPrint 등 다른 PDF 엔진 전환 시 fallback 작성 필요 (이게
Playwright 채택 근거 중 하나).

## 가로/세로 모드

`worksheet.orientation` 으로 토글:

| 모드 | 페이지 크기 | 좌우 패딩 | 활용 |
|---|---|---|---|
| portrait | 210mm × 297mm | 18~22mm | 일반 워크시트 |
| landscape | 297mm × 210mm | 26~30mm | 긴 영어 문장 / 좌우 비교 레이아웃 |

가로 모드 패딩이 더 큰 이유: A4 가로폭 (297mm) 전체에 본문이 깔리면 한 줄이 너무
길어 시선 이동 피로. 패딩으로 본문폭 ~240mm 로 묶음.

## Stage 진행 상태

- [x] Stage 0 — 자산 도입 (이 PR)
- [ ] Stage 1 — schema 갭 해소 (subtitle, orientation, instruction,
  WorksheetItem.label) + Branding ↔ academy 어댑터 (Phase 1 baseline 후)
- [ ] Stage 2 — Playwright 도입 + 렌더 PoC (FastAPI 라우트 `GET /worksheets/{id}/preview`,
  `POST /worksheets/{id}/export.pdf`) + 에디터 산출 HTML 호환성 검증
- [ ] Stage 3 — Web preview UI + customizing (Phase 2 본격)
