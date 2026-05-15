# Visual Regression Guide — annotation 시각 비전 회귀 spec

**도입**: Stage F4 (와이프 검수) 전 자동 안전망 추가 (2026-05-15)
**대상 spec**: `apps/web/tests/e2e/visual_regression_annotation.spec.ts`
**companion spec**: `apps/web/tests/e2e/wrap_parity_stage_f3.spec.ts` (좌표 기반)

---

## 1. 왜 비전 회귀 spec 인가

좌표(Y줄번호) 기반 wrap_parity spec 은 텍스트 *위치* 정합을 검증하지만, 다음 유형의 회귀는 감지하지 못한다:

- annotation mark 의 색상 변경 (highlight 12색 팔레트)
- underline / bracket 두께 또는 스타일 변경
- top_label / bottom_label 폰트 크기 / 색상 변경
- paragraph 분리 여백(line-height) 변경
- annotation mark 경계 모서리 굴곡 추가/제거

2026-05-15 와이프 검수에서 "엉망이야 훨씬 나빠졌어" 보고 사례가 이 유형에 해당. 좌표 spec 은 통과했지만 픽셀 시각이 회귀했다.

비전 spec 은 `toHaveScreenshot()` 으로 *픽셀 단위* diff 를 자동 감지한다.

---

## 2. 검증 대상 (Zero Waste 지문)

| 이름 | 단락 내용 | annotation |
|------|-----------|------------|
| C1 | These supermarkets and grocery stores... | highlight + underline 동시 |
| C2 | both seller and buyer work together... | top_label + bracket 동시 |
| C3 | Currently, there are more than... | bracket 단독 ({}) |
| FULL | Zero-waste 전체 7 단락 | paragraph 분리 + padding 시각 |

---

## 3. 베이스라인 생성 / 갱신

### 첫 생성

```bash
cd apps/web
pnpm exec playwright test visual_regression_annotation --update-snapshots
```

베이스라인 파일 위치:
```
apps/web/tests/e2e/visual_regression_annotation.spec.ts-snapshots/
  c1-highlight-underline-chromium-darwin.png
  c1-top-label-chromium-darwin.png
  c2-label-bracket-chromium-darwin.png
  c2-bracket-paren-chromium-darwin.png
  c3-bracket-curly-chromium-darwin.png
  c3-bracket-curly-span-chromium-darwin.png
  full-zero-waste-7paragraphs-chromium-darwin.png
  full-second-paragraph-chromium-darwin.png
```

### 의도적 시각 변경 후 베이스라인 갱신 워크플로우

1. 시각 변경 코드 fix 적용 (annotation mark CSS / Tiptap extension 변경)
2. 변경 후 시각이 *의도한 대로* 렌더링되는지 직접 확인 (`/preview/server-tiptap?scenario=C1` 등)
3. 베이스라인 갱신:
   ```bash
   pnpm exec playwright test visual_regression_annotation --update-snapshots
   ```
4. 갱신된 스크린샷 파일을 git 에 포함해서 commit
5. PR 본문에 Before/After 스크린샷 첨부 (와이프 시각 검수 가능하도록)

---

## 4. tolerance 설정

```typescript
const SCREENSHOT_OPTIONS = {
  maxDiffPixelRatio: 0.02,  // 전체 픽셀 2% 이내 diff 허용
  threshold: 0.2,            // 개별 픽셀 색상 diff 20% 이내 허용
};
```

- `maxDiffPixelRatio: 0.02` — 폰트 subpixel hinting 미세 차이(anti-aliasing)로 인한 false positive 방지. 실질 annotation 시각 변경은 2% 이상 diff 를 만든다.
- `threshold: 0.2` — 개별 픽셀 색상의 20% 이내 차이. 동일 색상이지만 subpixel 렌더 방식 차이로 생기는 경계 픽셀 1~2개 처리.

annotation 픽셀 값 변경 금지 정책 (memory: `feedback_pdf_annotation_visual.md`) 과 맞물려, 의도하지 않은 변경은 모두 실패로 감지한다.

---

## 5. 환경별 차이 처리 (local Mac vs CI Linux)

### 문제

Playwright 비전 spec 의 가장 큰 함정은 환경 의존성:

- **폰트 렌더링**: macOS (Core Text) vs Linux (FreeType) 의 subpixel hinting 차이
- **Chromium 버전**: OS 별 번들 버전이 다를 수 있음
- **디스플레이 DPR**: Retina Mac (DPR=2) 에서 생성한 스크린샷은 CI (DPR=1) 와 크기 불일치

### 현재 대응

1. `deviceScaleFactor: 1` 고정 (`playwright.config.ts`) — Retina 함정 방지
2. `viewport: { width: 1280, height: 720 }` 고정 — 크기 일관성
3. `page.waitForLoadState("networkidle")` — Pretendard CDN 폰트 로드 완료 보장
4. Playwright 기본 스냅샷 파일명에 OS suffix 포함 (`-darwin.png`, `-linux.png`) — 환경별 별도 베이스라인 자동 분리

### Docker 컨테이너 권장 (CI 환경 일치)

장기적으로 CI 와 동일한 환경에서 베이스라인을 생성하는 것이 가장 안정적:

```bash
# Playwright 공식 Docker 이미지 사용
docker run --rm -v $(pwd):/work -w /work \
  mcr.microsoft.com/playwright:v1.49.0-jammy \
  pnpm exec playwright test visual_regression_annotation --update-snapshots
```

현재는 local Mac 베이스라인으로 시작하고, CI 에서 실패하면 Linux 베이스라인을 별도 생성하는 방식 채택. Phase 4 (클라우드 배포) 진입 전 Docker 워크플로우 전환 권장.

---

## 6. 테스트 실행

### 비전 spec 단독 실행

```bash
cd apps/web
pnpm exec playwright test visual_regression_annotation
```

### 전체 e2e (wrap_parity + 비전) 통합 실행

```bash
cd apps/web
pnpm exec playwright test
```

### UI 모드 (디버깅)

```bash
cd apps/web
pnpm exec playwright test visual_regression_annotation --ui
```

### 사전 조건

- Vite dev 서버 (`pnpm dev`) — playwright.config.ts 의 `webServer` 설정으로 자동 기동. `reuseExistingServer: true` (non-CI) 이므로 이미 실행 중이면 재사용.
- API 서버 불필요 — `/preview/server-tiptap` 라우트는 mock fixture 로 동작.

---

## 7. 회귀 실패 시 대응

### 실패 메시지 예시

```
Error: Screenshot comparison failed:
  11234 pixels (2.3%) are different.
  Received: tests/e2e/test-results/...-actual.png
  Expected: tests/e2e/visual_regression_annotation.spec.ts-snapshots/c1-highlight-underline-chromium-darwin.png
```

### 대응 흐름

1. `test-results/` 디렉토리의 `-actual.png`, `-diff.png` 확인
2. 의도한 변경인가?
   - **예**: 위 §3 워크플로우대로 베이스라인 갱신 + PR 스크린샷 첨부
   - **아니오**: 어떤 코드 변경이 원인인지 추적 (`git bisect` 또는 직접 확인) → revert 또는 fix
3. annotation 픽셀 값 변경이라면 반드시 와이프 검수 후 베이스라인 갱신 (단독 판단 금지)

---

## 8. 후속 작업

- Phase 3 (변형문제) 진입 시 변형문제 렌더링 비전 spec 추가
- Phase 4 (클라우드 배포) 진입 전 Docker 기반 CI 베이스라인 워크플로우 전환
- 와이프 요청 시 화살표(arrow) annotation 비전 spec 추가 (현재 미구현 — ADR-0018 후속)
