import { afterEach, describe, expect, it, vi } from "vitest";

import {
  advancedReaderApi,
  documentIdFromSearch,
  sameOriginUrl,
} from "../src/api/client";
import { DOCUMENT_ID, metadata } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("same-origin API boundary", () => {
  it("[67] builds and fetches only relative same-origin Advanced Reader routes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(metadata), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const pdfUrl = advancedReaderApi.pdfUrl(DOCUMENT_ID);
    expect(pdfUrl).toBe(`/api/advanced-reader/documents/${DOCUMENT_ID}/pdf`);
    expect(pdfUrl).not.toMatch(/^https?:/u);
    await advancedReaderApi.getMetadata(DOCUMENT_ID);
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/advanced-reader/documents/${DOCUMENT_ID}`,
      expect.objectContaining({
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
      }),
    );
    expect(() => sameOriginUrl("https://example.test/reader.pdf")).toThrow();
  });

  it("accepts exactly one canonical document_id query parameter", () => {
    expect(documentIdFromSearch(`?document_id=${DOCUMENT_ID}`)).toBe(DOCUMENT_ID);
    expect(documentIdFromSearch(`?document_id=${DOCUMENT_ID}&url=https://example.test`)).toBeNull();
    expect(documentIdFromSearch("?document_id=../private.pdf")).toBeNull();
  });
});
