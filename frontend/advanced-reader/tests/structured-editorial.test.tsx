import { useState } from "react";
import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StructuredEditorial } from "../src/study/StructuredEditorial";
import {
  structuredDraft,
  structuredValues,
  type StructuredDocument,
} from "../src/study/structured-state";
afterEach(cleanup);
function open(initial: StructuredDocument) {
  let current = initial;
  const updates: StructuredDocument[] = [];
  function Harness() {
    const [value, setValue] = useState(initial);
    return (
      <StructuredEditorial
        value={value}
        change={(operation) => {
          current = operation(current);
          updates.push(current);
          setValue(current);
        }}
      />
    );
  }
  render(<Harness />);
  fireEvent.click(screen.getByText("Pie de página y marca de agua"));
  return { current: () => current, updates };
}
it("opens legacy notes with missing editorial sections without silently adding defaults, then changes only requested settings", () => {
  const original = structuredValues(
    structuredDraft("cornell"),
    "cornell",
  ).document;
  delete original.attribution;
  delete original.watermark;
  original.extension = { keep: ["á"] };
  const initial = structuredClone(original),
    probe = open(original);
  expect(screen.getByLabelText("Contenido del pie")).toHaveValue("auto");
  expect(screen.getByLabelText("Posición del pie")).toHaveValue("bottom_right");
  expect(screen.getByLabelText("Posición de la marca")).toHaveValue("center");
  expect(screen.getByLabelText("Escala de la marca")).toHaveValue(0.4);
  expect(screen.getByLabelText("Opacidad de la marca")).toHaveValue(0.05);
  expect(screen.getByLabelText("Marca en todas las páginas")).toBeChecked();
  expect(probe.updates).toHaveLength(0);
  fireEvent.change(screen.getByLabelText("Autor del pie"), {
    target: { value: "Autora" },
  });
  fireEvent.change(screen.getByLabelText("Texto de la marca de agua"), {
    target: { value: "COPIA" },
  });
  expect(probe.current()).toEqual({
    ...initial,
    attribution: { author: "Autora" },
    watermark: { text: "COPIA" },
  });
  expect(original).toEqual(initial);
});
it("does not replace a valid watermark parameter with an empty or nonnumeric value and accepts an explicit zero", () => {
  const original = structuredValues(structuredDraft("cpi"), "cpi").document;
  const probe = open(original),
    opacity = screen.getByLabelText("Opacidad de la marca");
  fireEvent.change(opacity, { target: { value: "" } });
  expect(probe.updates).toHaveLength(0);
  expect(probe.current()).toEqual(original);
  fireEvent.change(opacity, { target: { value: "0" } });
  expect(probe.current().watermark).toMatchObject({ opacity: 0, scale: 0.4 });
  expect(probe.current().pages).toEqual(original.pages);
});
