import { describe, expect, it } from "vitest";
import { normalizeRedistributedLicense, stripAsciiLineEnds } from "../scripts/text-normalization.mjs";

describe("resource text normalization", () => {
  it("keeps indentation, Unicode, nonbreaking spaces and every line terminator", () => {
    expect(stripAsciiLineEnds("  α \t\nβ\t \rγ \u2028δ\t\u2029x\u00a0 \t")).toBe("  α\nβ\rγ\u2028δ\u2029x\u00a0");
  });
  it("normalizes CRLF and keeps exactly one final LF in redistributed licenses", () => {
    expect(normalizeRedistributedLicense("License\t \r\n\r\n\t\r\n")).toBe("License\n");
    expect(normalizeRedistributedLicense("")).toBe("\n");
    expect(normalizeRedistributedLicense("License\r")).toBe("License\r\n");
  });
  it("preserves long interior whitespace and newlines followed by actual text", () => {
    const spaces = "x" + " ".repeat(100_000) + "y";
    const lines = "x" + "\n".repeat(100_000) + "y";
    expect(stripAsciiLineEnds(spaces)).toBe(spaces);
    expect(normalizeRedistributedLicense(lines)).toBe(lines + "\n");
    expect(stripAsciiLineEnds("x" + " ".repeat(100_000))).toBe("x");
  });
});
