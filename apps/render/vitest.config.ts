/// <reference types="vitest" />
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Node 환경 — jsdom 은 코드에서 직접 import (polyfill 수동 주입)
    environment: "node",
    globals: true,
    // 타임아웃 증가 — ProseMirror View boot 가 느릴 수 있음
    testTimeout: 30000,
    hookTimeout: 30000,
  },
});
