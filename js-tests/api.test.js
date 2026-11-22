import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  api,
  apiGetAll,
  apiRequest,
} from "../satgonetem_gui/static/api.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, { ok: true })));

    await expect(api.get("/api/status")).resolves.toEqual({ ok: true });
  });

  it("throws an ApiError for the common error envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(404, { ok: false, error: "Not found" })),
    );

    await expect(api.get("/api/missing")).rejects.toMatchObject({
      name: "ApiError",
      message: "Not found",
      status: 404,
    });
  });

  it("reports network errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );

    await expect(api.get("/api/status")).rejects.toBeInstanceOf(ApiError);
  });

  it("rejects malformed JSON and unexpected non-JSON success bodies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("{not-json", {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
      ),
    );
    await expect(api.get("/api/status")).rejects.toMatchObject({
      message: "Invalid JSON response.",
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("<html>proxy</html>", {
            status: 200,
            headers: { "content-type": "text/html" },
          }),
      ),
    );
    await expect(api.get("/api/status")).rejects.toMatchObject({
      message: "Unexpected non-JSON response.",
    });
  });

  it("surfaces the first validation detail in the message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(422, {
          ok: false,
          error: "Invalid request.",
          details: [{ loc: ["body", "duration"], msg: "Input should be >= 1" }],
        }),
      ),
    );

    await expect(api.get("/api/status")).rejects.toMatchObject({
      message: "Invalid request. (Input should be >= 1)",
      status: 422,
    });
  });

  it("fetches every page of a bounded list", async () => {
    const requested = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        requested.push(url);
        const offset = Number(new URL(url, "http://test").searchParams.get("offset"));
        const page = offset === 0 ? [{ id: 1 }, { id: 2 }] : [{ id: 3 }];
        return jsonResponse(200, page);
      }),
    );

    await expect(apiGetAll("/api/items", { pageSize: 2 })).resolves.toEqual([
      { id: 1 },
      { id: 2 },
      { id: 3 },
    ]);
    expect(requested).toEqual([
      "/api/items?limit=2&offset=0",
      "/api/items?limit=2&offset=2",
    ]);
  });

  it("times out while reading a stalled response body", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          new ReadableStream({
            start() {
              /* never enqueue or close */
            },
          }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        ),
      ),
    );

    const request = apiRequest("/api/status", { timeout: 10 });
    const assertion = expect(request).rejects.toMatchObject({
      message: "Request timed out.",
    });
    await vi.advanceTimersByTimeAsync(11);
    await assertion;
    vi.useRealTimers();
  });

  it("reports caller cancellation as aborted, not timed out", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_path, options) =>
          new Promise((_resolve, reject) => {
            options.signal.addEventListener("abort", () =>
              reject(new Error("aborted")),
            );
          }),
      ),
    );

    const controller = new AbortController();
    const request = apiRequest("/api/status", { signal: controller.signal });
    controller.abort();

    await expect(request).rejects.toMatchObject({ message: "Request aborted." });
  });

  it("removes the caller abort listener when the request settles", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, { ok: true })));
    const signal = {
      aborted: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    };

    await apiRequest("/api/status", { signal });

    expect(signal.addEventListener).toHaveBeenCalledTimes(1);
    expect(signal.removeEventListener).toHaveBeenCalledWith(
      "abort",
      signal.addEventListener.mock.calls[0][1],
    );
  });

  it("aborts a request that exceeds its timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_path, options) =>
          new Promise((_resolve, reject) => {
            options.signal.addEventListener("abort", () =>
              reject(new Error("aborted")),
            );
          }),
      ),
    );

    const request = apiRequest("/api/status", { timeout: 10 });
    const assertion = expect(request).rejects.toMatchObject({
      message: "Request timed out.",
    });
    await vi.advanceTimersByTimeAsync(11);
    await assertion;
    vi.useRealTimers();
  });
});
