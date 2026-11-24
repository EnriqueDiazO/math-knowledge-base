import { beforeEach, describe, expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/react";
import { FigurePreview } from "../src/study/FigurePreview";
import { pngDataUri } from "../src/study/image-data";
import { studyBinary, studyRequest } from "../src/study/api";
vi.mock("../src/study/api", () => ({
  studyRequest: vi.fn(),
  studyBinary: vi.fn(),
  downloadDocument: vi.fn(),
}));
beforeEach(() => {
  document.body.replaceChildren();
  vi.clearAllMocks();
});
describe("CSP-compatible compiled raster preview", () => {
  it("uses a PNG data URL and enables enlargement only after decoding", async () => {
    vi.mocked(studyRequest).mockResolvedValue({
      state: "ready",
      preview_id: "owned",
      message: "Vista previa compilada.",
    });
    vi.mocked(studyBinary).mockResolvedValue(
      new Blob(["png"], { type: "image/png" }),
    );
    const host = document.createElement("div");
    document.body.append(host);
    const preview = new FigurePreview({
      library_id: "library",
      runtime_id: "runtime",
    });
    preview.show("original TikZ", host);
    const image = host.querySelector("img")!,
      zoom = [...host.querySelectorAll("button")].find(
        (b) => b.textContent === "Ampliar figura",
      )!;
    await waitFor(() => expect(image.src).toMatch(/^data:image\/png;base64,/u));
    expect(zoom.disabled).toBe(true);
    Object.defineProperty(image, "naturalWidth", { value: 20 });
    image.dispatchEvent(new Event("load"));
    expect(zoom.disabled).toBe(false);
    zoom.click();
    expect(document.querySelector<HTMLImageElement>("dialog img")!.src).toBe(
      image.src,
    );
    preview.show("original TikZ", host);
    expect(studyRequest).toHaveBeenCalledTimes(1);
    preview.destroy();
    expect(document.querySelector("dialog")).toBeNull();
  });
  it("retains the protected code and explains a display failure", async () => {
    vi.mocked(studyRequest).mockResolvedValue({
      state: "ready",
      preview_id: "owned",
      message: "Compiled",
    });
    vi.mocked(studyBinary).mockResolvedValue(
      new Blob(["png"], { type: "image/png" }),
    );
    const host = document.createElement("div");
    host.textContent = "Original protected source";
    document.body.append(host);
    const preview = new FigurePreview({
      library_id: "library",
      runtime_id: "runtime",
    });
    preview.show("source", host);
    const image = host.querySelector("img")!;
    await waitFor(() => expect(image.src).toMatch(/^data:/u));
    image.dispatchEvent(new Event("error"));
    expect(host.textContent).toContain("Original protected source");
    expect(host.textContent).toContain("No pudimos mostrar la figura");
    preview.destroy();
  });
  it("rejects an unexpected non-raster response rather than putting HTML in an image", () => {
    expect(() =>
      pngDataUri(new Blob(["<script>bad()</script>"], { type: "text/html" })),
    ).toThrow(/PNG/u);
  });
});

it("replaces a compiled document snapshot after editing and retains the editor on compilation failure", async () => {
  vi.mocked(studyRequest).mockResolvedValue({state:"failed", message:"Macro no disponible", diagnostic:"Undefined control sequence"});
  const host = document.createElement("div"); document.body.append(host);
  const preview = new FigurePreview({library_id:"library",runtime_id:"runtime"});
  preview.showDocument("Primer borrador",host,"Título");
  await waitFor(() => expect(host.textContent).toContain("Macro no disponible"));
  expect(studyRequest).toHaveBeenLastCalledWith("/document-previews", expect.anything(), {source:"Primer borrador",title:"Título",kind:"document",refresh:false},expect.anything());
  preview.showDocument("Segundo borrador",host,"Título nuevo");
  await waitFor(() => expect(studyRequest).toHaveBeenCalledTimes(2));
  expect(host.querySelectorAll(".figure-preview")).toHaveLength(1);
  expect(studyRequest).toHaveBeenLastCalledWith("/document-previews", expect.anything(), {source:"Segundo borrador",title:"Título nuevo",kind:"document",refresh:false},expect.anything());
  expect(host.textContent).toContain("Primera página");
  preview.destroy();
});
