/** Visibility controls and explicit thematic layout, without document lifecycle. */
import { element, button, selector } from "./ui";
import type { Data, View } from "./model";
import { thematicLayout, relax } from "./layout";
export function renderMapFilters(
  filters: HTMLElement,
  data: Data,
  view: View,
  refresh: () => void,
): void {
  filters.replaceChildren();
  const all = { value: "", text: "Todos" };
  const human = (a: string, b: string) => a.localeCompare(b, "es");
  selector(
    filters,
    "Fuente visible",
    [
      all,
      ...[...new Set(data.nodes.map((n) => n.source))]
        .sort(human)
        .map((s) => ({ value: s, text: s })),
    ],
    view.source,
    (v) => {
      view.source = v;
      refresh();
    },
  );
  selector(
    filters,
    "Tipo visible",
    [
      all,
      ...[...new Set(data.nodes.map((n) => n.tipo))]
        .sort(human)
        .map((s) => ({ value: s, text: s })),
    ],
    view.type,
    (v) => {
      view.type = v;
      refresh();
    },
  );
  selector(
    filters,
    "Relación visible",
    [all, ...data.relation_types.map((s) => ({ value: s, text: s }))],
    view.relation,
    (v) => {
      view.relation = v;
      refresh();
    },
  );
  button(
    view.frontOnly ? "Mostrar hemisferio posterior" : "Sólo hemisferio frontal",
    () => {
      view.frontOnly = !view.frontOnly;
      refresh();
    },
    filters,
  );
}
export function renderMapThemes(
  themes: HTMLElement,
  data: Data,
  view: View,
  refresh: () => void,
  rememberLayout: () => void,
): void {
  themes.replaceChildren();
  themes.append(
    element(
      "p",
      "Áreas: elige categorías temáticas explícitamente. Fuente, tipo y área son dimensiones distintas.",
      "hint",
    ),
  );
  const categories = [...new Set(data.nodes.flatMap((n) => n.categorias))].sort(
    (a, b) => a.localeCompare(b, "es"),
  );
  categories.forEach((area) => {
    const label = element("label", area),
      check = element("input");
    check.type = "checkbox";
    check.checked = view.areas!.includes(area);
    check.onchange = () => {
      if (check.checked && view.areas!.length >= 6) {
        check.checked = false;
        return;
      }
      view.areas = check.checked
        ? [...view.areas!, area]
        : view.areas!.filter((a) => a !== area);
      view.layoutDirty = true;
      renderMapThemes(themes, data, view, refresh, rememberLayout);
      refresh();
    };
    label.prepend(check);
    themes.append(label);
  });
  button(
    view.mandala ? "Desactivar estilo mandala" : "Activar estilo mandala",
    () => {
      view.mandala = !view.mandala;
      view.layoutDirty = true;
      renderMapThemes(themes, data, view, refresh, rememberLayout);
      refresh();
    },
    themes,
  );
  button(
    "Organizar por áreas",
    () => {
      if (!view.areas?.length) return;
      rememberLayout();
      view.points = thematicLayout(data, view);
      view.layoutDirty = true;
      refresh();
    },
    themes,
  );
  button(
    "Disposición orgánica: ensayo breve",
    () => {
      rememberLayout();
      view.points = relax(view.points, view.pinned ?? []);
      view.layoutDirty = true;
      refresh();
    },
    themes,
  );
}
