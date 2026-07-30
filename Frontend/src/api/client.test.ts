import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest, fetchList, fetchPage } from "./client";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
    json: async () => body,
  } as Response;
}

describe("api client", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("accessToken", "access-1");
    localStorage.setItem("refreshToken", "refresh-1");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetchList unwraps a paginated envelope", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ count: 2, next: null, previous: null, page: 1, page_size: 200, total_pages: 1, results: [{ id: 1 }, { id: 2 }] }),
    );
    const result = await fetchList<{ id: number }>("/clients/");
    expect(result).toEqual([{ id: 1 }, { id: 2 }]);
    // It requests a capped page size to preserve "load all" behaviour.
    expect(String(fetchMock.mock.calls[0][0])).toContain("page_size=200");
  });

  it("fetchList passes through a plain array (non-paginated action)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([{ id: 9 }]));
    const result = await fetchList<{ id: number }>("/meetings/upcoming/");
    expect(result).toEqual([{ id: 9 }]);
  });

  it("fetchPage returns metadata", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ count: 5, next: "x", previous: null, page: 1, page_size: 2, total_pages: 3, results: [{ id: 1 }] }),
    );
    const page = await fetchPage<{ id: number }>("/deals/?page=1");
    expect(page.count).toBe(5);
    expect(page.total_pages).toBe(3);
  });

  it("refreshes the access token on a 401 and retries once", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401)) // first protected call
      .mockResolvedValueOnce(jsonResponse({ access: "access-2" }, 200)) // refresh
      .mockResolvedValueOnce(jsonResponse({ id: 1, username: "me" }, 200)); // retry

    const result = await apiRequest<{ username: string }>("/auth/me/");
    expect(result.username).toBe("me");
    expect(localStorage.getItem("accessToken")).toBe("access-2");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    // The retry uses the new token.
    const retryInit = fetchMock.mock.calls[2][1] as RequestInit;
    expect((retryInit.headers as Record<string, string>).Authorization).toBe("Bearer access-2");
  });

  it("throws with the response body on a non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "nope", code: "bad" }, 400));
    await expect(apiRequest("/clients/")).rejects.toThrow(/nope/);
  });
});
