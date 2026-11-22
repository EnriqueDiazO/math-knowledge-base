import { describe, expect, it } from "vitest";
import { offlineInspectionText } from "../scripts/offline-validation.mjs";

describe("reviewed MathLive packaging expression", () => {
  it("recognizes only the hostname normalization comparison, without changing runtime code", () => {
    const source = 'new URL(assetBase).hostname===`cdn.jsdelivr.net`&&(assetBase+=`/`)';
    expect(offlineInspectionText(source)).not.toContain('cdn.jsdelivr.net');
    expect(source).toContain('cdn.jsdelivr.net');
  });
  it("leaves real network destinations, other expressions and injected suffixes forbidden", () => {
    for (const source of [
      'fetch("https://cdn.jsdelivr.net/mathlive")',
      'new URL(asset).hostname===`cdn.jsdelivr.net`&&(other+=`/`)',
      'const host="cdn.jsdelivr.net"',
      'new URL(a).hostname===`cdn.jsdelivr.net`&&(a+=`/`);fetch("https://cdn.jsdelivr.net/a")',
    ]) expect(offlineInspectionText(source)).toContain('cdn.jsdelivr.net');
  });
});
