import { Route, Routes } from "react-router-dom";
import { EditorPoc } from "./pages/EditorPoc";
import { Home } from "./pages/Home";

/**
 * 앱 라우팅 골격
 * - /        : 랜딩 페이지
 * - /editor  : Tiptap PoC (Sprint 0 #7)
 */
function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/editor" element={<EditorPoc />} />
    </Routes>
  );
}

export default App;
