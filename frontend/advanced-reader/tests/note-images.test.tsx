import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { NoteImages } from "../src/study/NoteImages";
import type { StudyContext } from "../src/study/api";
const context = {
  library_id: "library",
  runtime_id: "runtime",
  name: "Temporary",
  capabilities: ["structured-images"],
  preparation: {
    state: "ready",
    reason: "",
    version: "v1",
    notes_ready: true,
    reading_ready: true,
  },
} as StudyContext;
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
test("saved previews load on demand with library headers and revoke owned blob URLs", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        images: [
          {
            asset_id: "a",
            name: "Captura real.png",
            state: "ready",
            watermark: false,
          },
        ],
      }),
    })
    .mockResolvedValueOnce({
      ok: true,
      blob: async () => new Blob(["image"], { type: "image/png" }),
    });
  vi.stubGlobal("fetch", fetch);
  const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:owned"),
    revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  const view = render(
    <NoteImages context={context} family="cpi" identity="note" />,
  );
  expect(fetch).not.toHaveBeenCalled();
  const details = view.container.querySelector("details")!;
  details.open = true;
  fireEvent(details, new Event("toggle"));
  await screen.findByAltText("Captura real.png");
  await waitFor(() =>
    expect(screen.getByAltText("Captura real.png").getAttribute("src")).toBe(
      "blob:owned",
    ),
  );
  expect(fetch.mock.calls[1][1].headers["X-MathMongo-Library"]).toBe("library");
  view.unmount();
  expect(create).toHaveBeenCalledOnce();
  expect(revoke).toHaveBeenCalledWith("blob:owned");
  create.mockRestore();
  revoke.mockRestore();
});
test("closing the panel ignores a late image and never publishes another library resource", async () => {
  let resolve!: (value: unknown) => void;
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          images: [{ asset_id: "a", name: "Late.png", state: "ready" }],
        }),
      })
      .mockImplementationOnce(
        () =>
          new Promise((r) => {
            resolve = r;
          }),
      ),
  );
  const create = vi.spyOn(URL, "createObjectURL");
  const view = render(
    <NoteImages context={context} family="cornell" identity="note" />,
  );
  const details = view.container.querySelector("details")!;
  details.open = true;
  fireEvent(details, new Event("toggle"));
  await waitFor(() => expect(resolve).toBeDefined());
  view.unmount();
  await act(async () =>
    resolve({
      ok: true,
      blob: async () => new Blob(["late"], { type: "image/png" }),
    }),
  );
  expect(create).not.toHaveBeenCalled();
  create.mockRestore();
});
