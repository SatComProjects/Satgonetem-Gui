import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "../satgonetem_gui/static/api.js";

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
});
