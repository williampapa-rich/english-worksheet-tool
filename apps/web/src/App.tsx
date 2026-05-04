import { Route, Routes } from "react-router-dom";
import { EditorPoc } from "./pages/EditorPoc";
import { Home } from "./pages/Home";

/**
 * 앱 라우팅 골격
 * - /                     : 랜딩 페이지
 * - /editor               : Tiptap PoC — fixture 모드 (INITIAL_CONTENT 고정)
 * - /editor/:passageId    : API 로드 모드 — passage + annotations DB 에서 로드
 */
function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/editor" element={<EditorPoc />} />
      <Route path="/editor/:passageId" element={<EditorPoc />} />
    </Routes>
  );
}

export default App;
