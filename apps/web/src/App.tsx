import { Route, Routes } from "react-router-dom";
import { EditorPoc } from "./pages/EditorPoc";
import { Home } from "./pages/Home";
import { WorksheetListPage } from "./pages/WorksheetListPage";

/**
 * 앱 라우팅 골격
 * - /                     : 랜딩 페이지
 * - /editor               : Tiptap PoC — fixture 모드 (INITIAL_CONTENT 고정)
 * - /editor/:passageId    : API 로드 모드 — passage + annotations DB 에서 로드
 * - /worksheets           : 학생 자료 목록 (Stage E2-1)
 */
function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/editor" element={<EditorPoc />} />
      <Route path="/editor/:passageId" element={<EditorPoc />} />
      <Route path="/worksheets" element={<WorksheetListPage />} />
    </Routes>
  );
}

export default App;
