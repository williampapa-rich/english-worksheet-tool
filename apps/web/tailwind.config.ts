import type { Config } from "tailwindcss";

const config: Config = {
  // Tailwind가 스캔할 파일 범위
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
