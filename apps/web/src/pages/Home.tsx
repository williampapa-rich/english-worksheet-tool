import { Link } from "react-router-dom";

/**
 * 랜딩 페이지
 * Sprint 0 #6 — 간단한 환영 메시지 + 에디터 페이지 링크
 */
export function Home() {
  return (
    <main className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-8">
      <div className="max-w-lg w-full bg-white rounded-2xl shadow-sm border border-gray-100 p-10 text-center">
        <h1 className="text-3xl font-bold text-gray-900 mb-3">영어 학습 자료 생성 도구</h1>
        <p className="text-gray-500 mb-8 leading-relaxed">
          지문 하나로 구문분석 자료, 학생 배포용 자료, 변형문제를
          <br />
          일관된 콘텐츠 모델 위에서 생성·편집·내보내기합니다.
        </p>
        <div className="flex flex-col gap-3">
          <Link
            to="/passages/new"
            className="inline-block bg-blue-600 text-white font-medium px-6 py-3 rounded-xl hover:bg-blue-700 transition-colors"
          >
            Phase 3 — 새 지문 / 문제 입력 →
          </Link>
          <Link
            to="/worksheets"
            className="inline-block bg-white border border-gray-200 text-gray-700 font-medium px-6 py-3 rounded-xl hover:border-blue-300 hover:text-blue-600 transition-colors"
          >
            학생 자료 목록 →
          </Link>
          <Link
            to="/editor"
            className="inline-block bg-white border border-gray-200 text-gray-700 font-medium px-6 py-3 rounded-xl hover:border-blue-300 hover:text-blue-600 transition-colors"
          >
            구문분석 에디터 PoC →
          </Link>
        </div>
      </div>
    </main>
  );
}
