/**
 * preference.test.ts — getPreference / setPreference 단위 테스트 (C-2b)
 *
 * fetch 를 vi.stubGlobal 로 mock — msw 미도입 (기존 api.test.ts 패턴 따라감).
 *
 * 검증 항목:
 *   getPreference:
 *     - 200 → UserPreference 반환
 *     - 404 → null 반환
 *     - 422 → Error throw
 *   setPreference:
 *     - 200 (happy path) → 저장된 UserPreference 반환
 *     - 409 (version conflict) → PreferenceConflictError throw
 *     - 422 → Error throw
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { PreferenceConflictError, type UserPreference, getPreference, setPreference } from "./api";

// ---------------------------------------------------------------------------
// 헬퍼 — mock Response 생성
// ---------------------------------------------------------------------------

function mockOkResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: () => Promise.resolve(body),
    headers: new Headers(),
  } as unknown as Response;
}

function mockErrorResponse(status: number, body: unknown): Response {
  return {
    ok: false,
    status,
    statusText: status === 404 ? "Not Found" : status === 409 ? "Conflict" : "Unprocessable Entity",
    json: () => Promise.resolve(body),
    headers: new Headers(),
  } as unknown as Response;
}

// 테스트용 UserPreference fixture
function makePref(overrides: Partial<UserPreference> = {}): UserPreference {
  return {
    id: "pref-uuid-001",
    tenant_id: "tenant-uuid",
    user_id: "user-uuid",
    workspace_id: null,
    key: "preset.sentence_role",
    value: { presets: ["S", "V", "O", "OC", "SC"] },
    version: 1,
    created_at: "2026-05-05T00:00:00Z",
    updated_at: "2026-05-05T00:00:00Z",
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// getPreference
// ---------------------------------------------------------------------------

describe("getPreference", () => {
  it("200 응답 시 UserPreference 객체를 반환한다", async () => {
    const fixture = makePref();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockOkResponse(fixture)));

    const result = await getPreference("preset.sentence_role");

    expect(result).toEqual(fixture);
    expect(result?.version).toBe(1);
    expect(result?.value).toEqual({ presets: ["S", "V", "O", "OC", "SC"] });
  });

  it("404 응답 시 null 을 반환한다 (최초 진입 — DB 행 없음)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(mockErrorResponse(404, { detail: "Not found" }))
    );

    const result = await getPreference("preset.sentence_role");

    expect(result).toBeNull();
  });

  it("422 응답 시 Error 를 throw 한다 (unknown key)", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(mockErrorResponse(422, { detail: "Unknown preference key: bad.key" }))
    );

    await expect(getPreference("bad.key")).rejects.toThrow();
  });

  it("workspace_id 를 전달하면 query parameter 에 포함된다", async () => {
    const fixture = makePref({ workspace_id: "ws-001" });
    const mockFetch = vi.fn().mockResolvedValue(mockOkResponse(fixture));
    vi.stubGlobal("fetch", mockFetch);

    await getPreference("preset.sentence_role", "ws-001");

    const calledUrl: string = mockFetch.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("workspace_id=ws-001");
  });

  it("workspace_id 없으면 query parameter 가 포함되지 않는다", async () => {
    const fixture = makePref();
    const mockFetch = vi.fn().mockResolvedValue(mockOkResponse(fixture));
    vi.stubGlobal("fetch", mockFetch);

    await getPreference("preset.sentence_role");

    const calledUrl: string = mockFetch.mock.calls[0]?.[0] as string;
    expect(calledUrl).not.toContain("workspace_id");
  });
});

// ---------------------------------------------------------------------------
// setPreference
// ---------------------------------------------------------------------------

describe("setPreference", () => {
  it("200 응답 시 저장된 UserPreference 를 반환한다 (happy path)", async () => {
    const saved = makePref({ version: 2 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockOkResponse(saved)));

    const result = await setPreference(
      "preset.sentence_role",
      { presets: ["S", "V", "O"] },
      { version: 1 }
    );

    expect(result.version).toBe(2);
    expect(result.key).toBe("preset.sentence_role");
  });

  it("version 을 PATCH body 에 포함한다", async () => {
    const saved = makePref({ version: 3 });
    const mockFetch = vi.fn().mockResolvedValue(mockOkResponse(saved));
    vi.stubGlobal("fetch", mockFetch);

    await setPreference("preset.sentence_role", { presets: ["S"] }, { version: 2 });

    const callArgs = mockFetch.mock.calls[0];
    const requestBody = JSON.parse((callArgs?.[1] as RequestInit).body as string) as {
      version: number;
      value: unknown;
    };
    expect(requestBody.version).toBe(2);
  });

  it("version 없을 때 (최초 생성) body 에 version 포함 안 함", async () => {
    const saved = makePref({ version: 1 });
    const mockFetch = vi.fn().mockResolvedValue(mockOkResponse(saved));
    vi.stubGlobal("fetch", mockFetch);

    await setPreference("preset.sentence_role", { presets: ["S", "V"] });

    const callArgs = mockFetch.mock.calls[0];
    const requestBody = JSON.parse((callArgs?.[1] as RequestInit).body as string) as Record<
      string,
      unknown
    >;
    expect(requestBody).not.toHaveProperty("version");
  });

  it("409 응답 시 PreferenceConflictError 를 throw 한다", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          mockErrorResponse(409, { detail: "Version conflict. Current version: 3" })
        )
    );

    await expect(
      setPreference("preset.sentence_role", { presets: ["S"] }, { version: 1 })
    ).rejects.toThrow(PreferenceConflictError);
  });

  it("422 응답 시 일반 Error 를 throw 한다", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(mockErrorResponse(422, { detail: "Unknown preference key: bad.key" }))
    );

    await expect(setPreference("bad.key", { presets: [] })).rejects.toThrow(Error);
    // PreferenceConflictError 가 아님을 확인
    await expect(setPreference("bad.key", { presets: [] })).rejects.not.toThrow(
      PreferenceConflictError
    );
  });

  it("PATCH method 와 Content-Type: application/json 으로 전송한다", async () => {
    const saved = makePref();
    const mockFetch = vi.fn().mockResolvedValue(mockOkResponse(saved));
    vi.stubGlobal("fetch", mockFetch);

    await setPreference("preset.sentence_role", { presets: ["S"] });

    const callArgs = mockFetch.mock.calls[0];
    const options = callArgs?.[1] as RequestInit;
    expect(options.method).toBe("PATCH");
    expect((options.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });
});
