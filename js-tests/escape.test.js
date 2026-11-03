import { describe, expect, it } from "vitest";

import { escapeHtml } from "../satgonetem_gui/static/escape.js";

describe("escapeHtml", () => {
  it("escapes text and quoted attributes", () => {
    expect(escapeHtml(`<a href="x">'&`)).toBe(
      "&lt;a href=&quot;x&quot;&gt;&#39;&amp;",
    );
  });

  it("handles nullish values", () => {
    expect(escapeHtml(null)).toBe("");
    expect(escapeHtml(undefined)).toBe("");
  });
});
