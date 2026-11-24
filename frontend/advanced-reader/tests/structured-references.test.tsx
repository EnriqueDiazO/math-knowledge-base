import { afterEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { StructuredFields } from "../src/study/StructuredFields";
import {
  structuredDraft,
  structuredValues,
} from "../src/study/structured-state";
import type { StudyContext } from "../src/study/api";
vi.mock("../src/study/SourcePicker", () => ({
  SourcePicker: ({ choose }: { choose: (id: string) => void }) => (
    <button onClick={() => choose("source")}>Elegir fuente de prueba</button>
  ),
}));
vi.mock("../src/study/ReferencePicker", () => ({
  ReferencePicker: ({ changed }: { changed: (id: string) => void }) => (
    <button onClick={() => changed("reference")}>
      Elegir referencia de prueba
    </button>
  ),
}));
const context = { library_id: "owned", runtime_id: "runtime" } as StudyContext;
const values = structuredValues(structuredDraft("cornell"), "cornell");
const props = {
  context,
  family: "cornell" as const,
  values,
  page: 0,
  region: "cue",
  locked: false,
  remove: false,
  setRemove: () => {},
  metadata: () => {},
  changePages: () => {},
  select: () => {},
  document: () => {},
};
const click = (name: string) =>
  fireEvent.click(screen.getByRole("button", { name }));
function choose() {
  fireEvent.click(screen.getByText("Insertar referencia bibliográfica"));
  click("Elegir fuente de prueba");
  click("Elegir referencia de prueba");
  click("Insertar cita en esta región");
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("a citation response for a region left behind cannot mutate either region", async () => {
  let resolve!: (value: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    ),
  );
  const previous = vi.fn(() => true),
    next = vi.fn(() => true),
    view = render(<StructuredFields {...props} citation={previous} />);
  choose();
  view.rerender(<StructuredFields {...props} region="main" citation={next} />);
  await act(async () => resolve(Response.json({ latex: "Cita tardía" })));
  expect(previous).not.toHaveBeenCalled();
  expect(next).not.toHaveBeenCalled();
});
it("a rejected insertion cannot announce that a citation was incorporated", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ latex: "Cita propuesta" })),
  );
  const insert = vi.fn(() => false);
  render(<StructuredFields {...props} citation={insert} />);
  choose();
  await screen.findByText(/No se incorporó la cita/);
  expect(insert).toHaveBeenCalledWith("Cita propuesta");
  expect(screen.queryByText(/Cita incorporada al borrador/)).toBeNull();
});
