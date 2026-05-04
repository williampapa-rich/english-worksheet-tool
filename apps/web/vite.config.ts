/// <reference types="vitest" />
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // @/ alias → src/ 디렉토리 단축 경로
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
  },
  test: {
    // jsdom 환경에서 React 컴포넌트 테스트
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    globals: true,
    // Playwright e2e 파일은 vitest 수집 대상에서 제외 (별도 `pnpm e2e` 로 실행)
    exclude: ["**/node_modules/**", "**/tests/e2e/**"],
  },
});
