import { Route, Routes } from "react-router-dom";
import { EditorPoc } from "./pages/EditorPoc";
import { Home } from "./pages/Home";
import { PassageNewPage } from "./pages/PassageNewPage";
import { WorksheetDetailPage } from "./pages/WorksheetDetailPage";
import { WorksheetEditPage } from "./pages/WorksheetEditPage";
import { WorksheetListPage } from "./pages/WorksheetListPage";
import { WorksheetNewPage } from "./pages/WorksheetNewPage";

/**
 * 앱 라우팅 골격
 * - /                     : 랜딩 페이지
 * - /editor               : Tiptap PoC — fixture 모드 (INITIAL_CONTENT 고정)
 * - /editor/:passageId    : API 로드 모드 — passage + annotations DB 에서 로드
 *                            (?embed=1 → 헤더 숨김, 통합 편집 페이지 임베드용)
 * - /passages/new         : 신규 지문/문제 입력 (Phase 3 — 변형문제 생성 진입점)
 * - /worksheets           : 학생 자료 목록 (Stage E2-1)
 * - /worksheets/new       : 신규 학생 자료 생성 (Stage E2-2)
 * - /worksheets/:id       : 학생 자료 상세 (Stage E2-3a/b)
 * - /worksheets/:id/edit  : 통합 편집 페이지 (Stage E2-3c) — 좌측 편집 + 우측 미리보기
 */
function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/editor" element={<EditorPoc />} />
      <Route path="/editor/:passageId" element={<EditorPoc />} />
      <Route path="/passages/new" element={<PassageNewPage />} />
      <Route path="/worksheets" element={<WorksheetListPage />} />
      <Route path="/worksheets/new" element={<WorksheetNewPage />} />
      <Route path="/worksheets/:id" element={<WorksheetDetailPage />} />
      <Route path="/worksheets/:id/edit" element={<WorksheetEditPage />} />
    </Routes>
  );
}

export default App;
