import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

// React 19 + React Router v7 진입점
const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("루트 DOM 엘리먼트(#root)를 찾을 수 없습니다.");
}

createRoot(rootEl).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
