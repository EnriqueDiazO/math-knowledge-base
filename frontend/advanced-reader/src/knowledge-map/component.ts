import "./style.css";
import { applyStudyTheme } from "./theme";
import { MapCanvas, colors } from "./canvas";
import { positions, unrotate, unit } from "./geometry";
import type { Vec } from "./geometry";
import {
  acceptResult,
  draftFor,
  freshView,
  intention,
  neighbors,
  visibleNodes,
  studyState,
  useSavedView,
} from "./model";
import type { Data, Draft, View, Goal } from "./model";
import { element, button, field, selector } from "./ui";
import { DocumentEditor } from "./document-editor";
import { openReader } from "./reader";
import { DraftVault, persistedView, storeView } from "./drafts";
import { thematicLayout, relax } from "./layout";

type Bridge = {
  parentElement: HTMLElement;
  data: Data;
  setTriggerValue: (key: string, value: unknown) => void;
};
const memory = new Map<string, View>();
const mounted = new WeakMap<HTMLElement, () => void>();
function readView(scope: string): View {
  if (memory.has(scope)) return memory.get(scope)!;
  const saved = persistedView(scope);
  if (saved?.camera && saved.points) return saved;
  try {
    const old = JSON.parse(
      sessionStorage.getItem("mathmongo-map-" + scope) ?? "null",
    ) as View | null;
    if (old?.camera && old.points) return old;
  } catch {
    /* A new view is still usable without storage. */
  }
  return freshView();
}
export default function render({
  parentElement,
  data,
  setTriggerValue,
}: Bridge): () => void {
  mounted.get(parentElement)?.();
  const view = readView(data.scope);
  memory.set(data.scope, view);
  view.mapUid ??= crypto.randomUUID();
  view.mapName ??= "Mi esfera de estudio";
  view.pinned ??= [];
  view.areas ??= [];
  view.goals ??= [];
  view.flatPoints ??= {};
  let vault = new DraftVault(data.scope, view.mapUid);
  let composer: DocumentEditor | undefined;
  let editorDialog: HTMLDialogElement | undefined;
  let readingDispose: (() => void) | undefined;
  let expansion: HTMLDialogElement | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const acknowledgedDraft = view.draft;
  const confirmingId = view.pending?.operation_id;
  if (
    data.result &&
    data.result.operation_id === view.pending?.operation_id &&
    view.pending?.action === "save_view"
  ) {
    view.points = positions(
      data.nodes.map((n) => n.key),
      view.points,
    );
    view.status = data.result;
    if (data.result.status === "saved") {
      view.viewRevision = data.result.view_revision;
      view.layoutDirty = false;
      view.pending = undefined;
    } else if (["invalid", "conflict"].includes(data.result.status))
      view.pending = undefined;
  } else {
    const insertion =
      view.pending && data.result?.key && view.draft
        ? { key: data.result.key, point: view.draft.point }
        : undefined;
    view.points = positions(
      data.nodes.map((n) => n.key),
      view.points,
      insertion,
    );
    acceptResult(data, view);
    if (
      acknowledgedDraft &&
      confirmingId &&
      data.result &&
      data.result.operation_id === confirmingId &&
      view.acknowledged === confirmingId
    ) {
      if (data.result.status === "saved") vault.complete(acknowledgedDraft);
      if (acknowledgedDraft.goalId && data.result.key) {
        const goal = view.goals.find((g) => g.id === acknowledgedDraft.goalId);
        if (goal) {
          goal.conceptKey = data.result.key;
          view.points[data.result.key] = goal.point;
          view.layoutDirty = true;
        }
      }
    }
  }
  if (view.pending && data.result?.operation_id !== view.pending.operation_id)
    view.status = {
      status: "uncertain",
      message:
        "Existe un envío sin confirmar. Reconcilia el mismo intento antes de continuar.",
    };
  if (view.draft) {
    view.draft.id ??= crypto.randomUUID();
    vault.put(view.draft);
  }
  const root = element("section", "", "knowledge-map");
  applyStudyTheme(root);
  root.setAttribute("aria-label", "Mapa de conocimiento editable");
  const toolbar = element("div", "", "toolbar");
  const filterPanel = element("details", "", "map-options");
  filterPanel.append(element("summary", "Filtros y áreas"));
  const filters = element("div", "", "filters"),
    themes = element("div", "", "thematic-controls");
  filterPanel.append(filters, themes);
  const status = element("div", "", "status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const layout = element("div", "", "layout"),
    stage = element("div", "", "stage"),
    aside = element("aside");
  aside.setAttribute("aria-label", "Ficha del concepto");
  const canvas = element("canvas");
  canvas.tabIndex = 0;
  canvas.setAttribute("role", "img");
  canvas.setAttribute(
    "aria-label",
    "Mapa. Arrastra el fondo para girar y un nodo para reubicarlo. Flechas para girar.",
  );
  root.append(toolbar, filterPanel, status, layout);
  layout.append(stage, aside);
  stage.append(canvas);
  const legend = element("details", "", "legend-details");
  legend.append(element("summary", "Leyenda y ayuda"));
  const legendItems = element("div", "", "legend");
  Object.entries(colors).forEach(([type, color]) => {
    const item = element("span", type);
    item.style.setProperty("--node-color", color);
    legendItems.append(item);
  });
  legend.append(
    legendItems,
    element(
      "p",
      "Puntos: conceptos. Arcos con flecha: relaciones guardadas. Rombo discontinuo: pendiente explícito. Manchas y pétalos: presentación de áreas, sin relaciones nuevas.",
      "hint",
    ),
  );
  stage.append(legend);
  const host =
    parentElement.querySelector(".knowledge-map-root") ?? parentElement;
  host.replaceChildren(root);
  const save = () => {
    if (view.draft) vault.put(view.draft);
    storeView(data.scope, view);
  };
  const scene = new MapCanvas(
    canvas,
    data,
    view,
    (key) => select(key),
    (point) => start("create", point),
    () => {
      save();
      renderStatus();
    },
    (key) => {
      view.focusedEdge = key;
      renderAside();
      redraw();
    },
  );
  const redraw = () => {
    scene.update(data);
    save();
  };
  const refresh = () => {
    renderAside();
    renderStatus();
    redraw();
  };
  const select = (key: string) => {
    if (key.startsWith("goal:")) {
      activateGoal(key.slice(5));
      return;
    }
    view.selected = key;
    view.auto = false;
    selection.value = key;
    scene.bringFront(key);
    renderAside();
    renderStatus();
    redraw();
  };
  const start = (
    action: Draft["action"],
    point: Vec = unrotate([0, 0, 1], view.camera),
    goal?: Goal,
  ) => {
    if (view.pending) {
      renderStatus();
      return;
    }
    if (view.draft) {
      vault.put(view.draft);
      closeEditor();
    }
    const candidate =
      goal?.point ??
      positions([...data.nodes.map((n) => n.key), "__draft__"], view.points, {
        key: "__draft__",
        point,
      }).__draft__;
    view.draft = draftFor(data, view, action, candidate);
    view.draft.id = crypto.randomUUID();
    if (goal) {
      view.draft.goalId = goal.id;
      view.draft.title = goal.label;
      goal.draftId = view.draft.id;
      goal.state = "working";
      view.layoutDirty = true;
    }
    view.auto = false;
    view.status = {
      status: "draft",
      message:
        "Borrador recuperable en este navegador; aún no es un concepto guardado.",
    };
    vault.put(view.draft);
    showEditor();
    redraw();
    renderStatus();
  };
  function closeEditor(): void {
    if (view.draft && composer) {
      view.draft.content = composer.value();
      view.draft.document = composer.snapshot();
      vault.put(view.draft);
    }
    composer?.destroy();
    composer = undefined;
    editorDialog?.remove();
    editorDialog = undefined;
    save();
  }
  function keepAndClose(): void {
    closeEditor();
    view.draft = undefined;
    view.status = {
      status: "draft",
      message:
        "Borrador local conservado. Puedes recuperarlo; no se publicó contenido nuevo.",
    };
    refresh();
    canvas.focus();
  }
  function showEditor(): void {
    if (!view.draft) return;
    const draft = view.draft;
    editorDialog?.remove();
    composer?.destroy();
    const dialog = element("dialog", "", "document-dialog editor-dialog");
    editorDialog = dialog;
    const header = element("header");
    header.append(
      element(
        "h2",
        draft.action === "edit"
          ? "Editar concepto"
          : draft.action === "connect"
            ? "Conectar conceptos"
            : "Escribir concepto",
      ),
    );
    const close = button("Conservar borrador y volver", keepAndClose, header);
    close.disabled = !!view.pending;
    dialog.append(header);
    const form = element("form");
    dialog.append(form);
    const meta = element("details");
    meta.open = draft.action === "connect";
    meta.append(element("summary", "Metadatos, fuente y referencia"));
    form.append(meta);
    const name = field(form, "Nombre", draft.title, (value) => {
      draft.title = value;
      vault.put(draft);
    });
    name.required = draft.action !== "connect";
    name.maxLength = 500;
    if (draft.action !== "edit" && draft.action !== "connect") {
      selector(
        meta,
        "Source administrada",
        data.sources.map((s) => ({ value: s.id, text: s.name })),
        draft.source,
        (value) => {
          draft.source = value;
          save();
        },
      );
      selector(
        meta,
        "Tipo de concepto",
        data.concept_types.map((s) => ({ value: s, text: s })),
        draft.type,
        (value) => {
          draft.type = value;
          save();
        },
      );
    }
    field(meta, "Categorías separadas por comas", draft.categories, (value) => {
      draft.categories = value;
      save();
    });
    field(
      meta,
      "Comentario",
      draft.comment,
      (value) => {
        draft.comment = value;
        save();
      },
      true,
    );
    if (draft.action !== "connect") {
      const writing = element("div");
      form.append(writing);
      composer = new DocumentEditor(
        writing,
        draft.content,
        (content, snapshot) => {
          draft.content = content;
          draft.document = snapshot;
          vault.put(draft);
        },
        draft.document,
      );
    }
    if (["connect", "create_connected"].includes(draft.action))
      relationFields(form, draft);
    const controls = element("div", "", "editor-actions");
    form.append(controls);
    const submit = element("button", "Guardar concepto", "primary");
    submit.type = "submit";
    submit.disabled =
      !!view.pending ||
      (draft.action.startsWith("create") && !data.sources.length);
    controls.append(submit);
    button(
      "Descargar borrador",
      () => {
        const url = URL.createObjectURL(
          new Blob([JSON.stringify(draft, null, 2)], {
            type: "application/json",
          }),
        );
        const link = element("a");
        link.href = url;
        link.download = "mathmongo-borrador.json";
        link.click();
        URL.revokeObjectURL(url);
      },
      controls,
    );
    if (!view.pending)
      button(
        "Descartar borrador…",
        () => {
          const confirmation = element("div", "", "discard-confirm");
          confirmation.append(
            element(
              "p",
              "¿Descartar este borrador local? Los conceptos ya guardados permanecerán.",
            ),
          );
          button(
            "Sí, descartar este borrador",
            () => {
              const id = draft.id!;
              composer?.destroy();
              composer = undefined;
              view.draft = undefined;
              vault.discard(id);
              dialog.remove();
              editorDialog = undefined;
              refresh();
            },
            confirmation,
          );
          button(
            "Seguir escribiendo",
            () => confirmation.remove(),
            confirmation,
          );
          controls.append(confirmation);
        },
        controls,
      );
    if (view.status?.status === "conflict" && draft.action === "edit")
      button(
        "Revisar versión actual",
        () => {
          const node = data.nodes.find((n) => n.key === draft.origin);
          if (!node) return;
          const review = element("section");
          review.append(
            element("p", `Versión actual de ${node.titulo}`),
            element("pre", node.contenido_latex),
          );
          button(
            "He revisado: usar esta versión como base",
            () => {
              draft.revision = node.revision;
              view.status = {
                status: "draft",
                message:
                  "Revisión actual adoptada explícitamente; borrador conservado.",
              };
              vault.put(draft);
              review.remove();
              renderStatus();
            },
            review,
          );
          controls.append(review);
        },
        controls,
      );
    form.onsubmit = (event) => {
      event.preventDefault();
      if (view.pending) return;
      if (composer && !composer.valid()) {
        view.status = {
          status: "draft",
          message:
            "Hay una fórmula en elaboración. El borrador está conservado; corrígela antes de confirmar.",
        };
        renderStatus();
        return;
      }
      draft.content = composer?.value() ?? draft.content;
      draft.submitted = true;
      vault.put(draft);
      view.pending = intention(draft, crypto.randomUUID());
      submitPending();
    };
    if (view.pending)
      form
        .querySelectorAll("input,select,textarea,button")
        .forEach((n) => ((n as HTMLInputElement).disabled = true));
    dialog.oncancel = (event) => {
      event.preventDefault();
      if (!view.pending) keepAndClose();
    };
    root.append(dialog);
    dialog.showModal();
  }
  function relationFields(parent: HTMLElement, draft: Draft): void {
    const preview = element("p", "", "preview");
    const update = () => {
      const origin =
          data.nodes.find((n) => n.key === draft.origin)?.titulo ??
          draft.origin,
        target =
          draft.action === "connect"
            ? (data.nodes.find((n) => n.key === draft.target)?.titulo ??
              "Destino")
            : draft.title;
      preview.textContent = `${draft.reverse ? target : origin} → [${draft.relation}] → ${draft.reverse ? origin : target}`;
      save();
      scene.request();
    };
    if (draft.action === "connect")
      selector(
        parent,
        "Destino",
        [
          { value: "", text: "Elegir concepto" },
          ...data.nodes.map((n) => ({
            value: n.key,
            text: `${n.titulo} · ${n.source}`,
          })),
        ],
        draft.target,
        (v) => {
          draft.target = v;
          update();
        },
      );
    selector(
      parent,
      "Tipo de relación",
      data.relation_types.map((s) => ({ value: s, text: s })),
      draft.relation,
      (v) => {
        draft.relation = v;
        update();
      },
    );
    const label = element("label", "Invertir sentido "),
      checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.checked = draft.reverse;
    checkbox.onchange = () => {
      draft.reverse = checkbox.checked;
      update();
    };
    label.append(checkbox);
    parent.append(label, preview);
    update();
  }
  function submitPending(): void {
    if (!view.pending) return;
    view.status = {
      status: "saving",
      message: "Guardando… espera la confirmación del servidor.",
    };
    closeEditor();
    save();
    renderStatus();
    setTriggerValue("intent", view.pending);
    timer = setTimeout(() => {
      view.status = {
        status: "uncertain",
        message:
          "No llegó la confirmación. Reconcilia el mismo intento; el borrador se conserva.",
      };
      save();
      renderStatus();
    }, 15000);
  }
  function renderStatus(): void {
    status.replaceChildren();
    status.dataset.state = view.status?.status ?? "ready";
    status.append(
      element(
        "span",
        view.status?.message ??
          `${data.nodes.length} conceptos · ${data.edges.length} relaciones`,
      ),
    );
    if (!vault.available)
      status.append(
        element(
          "strong",
          " El almacenamiento local no está disponible: descarga el borrador antes de cerrar.",
        ),
      );
    const chosen = data.nodes.find((n) => n.key === view.selected);
    if (chosen && !visibleNodes(data, view).some((n) => n.key === chosen.key)) {
      status.append(
        element("span", " · Guardado fuera de los filtros activos."),
      );
      button(
        "Mostrar concepto guardado",
        () => {
          view.source = "";
          view.type = "";
          view.relation = "";
          view.neighborhood = false;
          renderFilters();
          refresh();
        },
        status,
      );
    }
    if (
      view.pending &&
      ["pending", "uncertain", "partial"].includes(view.status?.status ?? "")
    )
      button("Reconciliar el mismo intento", submitPending, status, true);
    if (view.pending?.action === "edit" && view.status?.status === "partial")
      button(
        "Revisar edición parcial con mi borrador",
        () => {
          view.pending = undefined;
          view.status = {
            status: "conflict",
            message: "Conserva la ficha parcial y revisa el contenido actual.",
          };
          showEditor();
          renderStatus();
        },
        status,
      );
    status.append(
      element(
        "span",
        view.layoutDirty ? " · Disposición sin guardar" : "",
        "layout-state",
      ),
    );
  }
  function renderAside(): void {
    aside.replaceChildren();
    const node = data.nodes.find((n) => n.key === view.selected);
    if (!node) {
      aside.append(
        element("h3", "Explorar y construir"),
        element(
          "p",
          "Selecciona un concepto para leerlo o crear una conexión.",
        ),
      );
      renderGoals();
      return;
    }
    aside.append(
      element("h3", node.titulo, "selected-title"),
      element("p", `${node.tipo} · ${node.source}`, "hint"),
    );
    const memberships = (view.areas ?? []).filter((a) =>
      node.categorias.includes(a),
    );
    aside.append(
      element(
        "p",
        memberships.length
          ? memberships.join(" · ")
          : "Sin clasificar en las áreas elegidas",
        "area-membership",
      ),
    );
    const actions = element("div", "", "actions");
    aside.append(actions);
    button(
      "Leer concepto",
      () => {
        view.auto = false;
        readingDispose?.();
        view.reader = node.key;
        save();
        readingDispose = openReader(root, node, view.textSize ?? 19, () => {
          view.reader = undefined;
          readingDispose = undefined;
          save();
          canvas.focus();
        });
      },
      actions,
      true,
    );
    button("Editar ficha", () => start("edit"), actions);
    button(
      "Crear conectado",
      () => start("create_connected", view.points[node.key]),
      actions,
    );
    button("Conectar con…", () => start("connect"), actions);
    button(
      "Abrir nota / edición avanzada",
      () => {
        save();
        setTriggerValue("open_note", {
          key: node.key,
          nonce: crypto.randomUUID(),
        });
      },
      actions,
    );
    button(
      view.neighborhood ? "Mostrar todo el mapa" : "Sólo conexiones directas",
      () => {
        view.neighborhood = !view.neighborhood;
        refresh();
      },
      actions,
    );
    const movement = element("details");
    movement.append(element("summary", "Reubicar y fijar nodo"));
    button(
      view.pinned!.includes(node.key) ? "Desfijar posición" : "Fijar posición",
      () => {
        view.pinned = view.pinned!.includes(node.key)
          ? view.pinned!.filter((k) => k !== node.key)
          : [...view.pinned!, node.key];
        view.layoutDirty = true;
        refresh();
      },
      movement,
    );
    const move = (x: number, y: number) => {
      scene.relocateSelected(x, y);
      refresh();
    };
    button("Mover nodo a la izquierda", () => move(-0.08, 0), movement);
    button("Mover nodo a la derecha", () => move(0.08, 0), movement);
    button("Mover nodo arriba", () => move(0, 0.08), movement);
    button("Mover nodo abajo", () => move(0, -0.08), movement);
    aside.append(movement);
    const details = element("details");
    details.append(
      element("summary", "Datos e identidad"),
      element("p", node.key),
      element("p", node.comentario),
    );
    aside.append(details);
    aside.append(element("h3", "Relaciones"));
    data.edges
      .filter((e) => e.from === node.key || e.to === node.key)
      .forEach((edge) => {
        const from =
            data.nodes.find((n) => n.key === edge.from)?.titulo ?? edge.from,
          to = data.nodes.find((n) => n.key === edge.to)?.titulo ?? edge.to;
        const item = button(
          `${edge.from === node.key ? "Saliente" : "Entrante"}: ${from} → ${edge.tipo.replaceAll("_", " ")} → ${to}`,
          () => {
            view.focusedEdge = edge.key;
            view.auto = false;
            view.neighborhood = false;
            scene.bringFront(edge.from);
            renderAside();
            redraw();
          },
          aside,
        );
        item.className = "relation-item";
        item.setAttribute(
          "aria-pressed",
          String(view.focusedEdge === edge.key),
        );
        if (view.focusedEdge === edge.key) {
          const summary = element(
            "p",
            `Origen: ${from}. Relación: ${edge.tipo.replaceAll("_", " ")}. Destino: ${to}. Dirección: origen → destino.`,
            "edge-summary",
          );
          aside.append(summary);
          button(
            "Ir al otro extremo",
            () => select(edge.from === node.key ? edge.to : edge.from),
            aside,
          );
          button(
            "Quitar enfoque de relación",
            () => {
              view.focusedEdge = undefined;
              refresh();
            },
            aside,
          );
        }
      });
    const near = neighbors(data, node.key);
    if (near.length) aside.append(element("h3", "Vecinos reales"));
    near.forEach(
      (n) =>
        (button(n.titulo, () => select(n.key), aside).className = "neighbor"),
    );
    renderGoals();
  }
  function renderGoals(): void {
    if (!view.goals?.length) return;
    aside.append(element("h3", "Objetivos explícitos"));
    view.goals.forEach((goal) => {
      const label = {
        pending: "Pendiente",
        working: "En elaboración",
        reviewed: "Revisado por mí",
      }[goal.state];
      button(
        `${label}: ${goal.label}`,
        () => activateGoal(goal.id),
        aside,
      ).className = "goal-item";
      if (goal.conceptKey)
        button(
          goal.state === "reviewed"
            ? "Volver a En elaboración"
            : "Marcar Revisado por mí",
          () => {
            goal.state = goal.state === "reviewed" ? "working" : "reviewed";
            view.layoutDirty = true;
            refresh();
          },
          aside,
        );
    });
    aside.append(
      element(
        "p",
        `${view.goals.filter((g) => g.state === "reviewed").length} de ${view.goals.length} objetivos marcados por ti. No mide dominio ni valida la matemática.`,
        "hint",
      ),
    );
  }
  function activateGoal(id: string): void {
    const goal = view.goals!.find((g) => g.id === id);
    if (!goal) return;
    if (goal.conceptKey) {
      select(goal.conceptKey);
      return;
    }
    const saved = goal.draftId ? vault.get(goal.draftId) : undefined;
    if (saved) {
      view.draft = saved;
      showEditor();
    } else start("create", goal.point, goal);
  }
  function renderFilters(): void {
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
      view.frontOnly
        ? "Mostrar hemisferio posterior"
        : "Sólo hemisferio frontal",
      () => {
        view.frontOnly = !view.frontOnly;
        refresh();
      },
      filters,
    );
  }
  function renderThemes(): void {
    themes.replaceChildren();
    themes.append(
      element(
        "p",
        "Áreas: elige categorías temáticas explícitamente. Fuente, tipo y área son dimensiones distintas.",
        "hint",
      ),
    );
    const categories = [
      ...new Set(data.nodes.flatMap((n) => n.categorias)),
    ].sort((a, b) => a.localeCompare(b, "es"));
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
        renderThemes();
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
        renderThemes();
        refresh();
      },
      themes,
    );
    button(
      "Organizar por áreas",
      () => {
        if (!view.areas?.length) return;
        scene.rememberLayout();
        view.points = thematicLayout(data, view);
        view.layoutDirty = true;
        refresh();
      },
      themes,
    );
    button(
      "Disposición orgánica: ensayo breve",
      () => {
        scene.rememberLayout();
        view.points = relax(view.points, view.pinned ?? []);
        view.layoutDirty = true;
        refresh();
      },
      themes,
    );
  }
  function expand(): void {
    if (expansion) {
      expansion.close();
      return;
    }
    const dialog = element("dialog", "", "expanded-map");
    expansion = dialog;
    host.append(dialog);
    dialog.append(root);
    view.expanded = true;
    dialog.onclose = () => {
      host.append(root);
      view.expanded = false;
      dialog.remove();
      expansion = undefined;
      expandButton.textContent = "Expandir mapa";
      scene.request();
      save();
    };
    dialog.showModal();
    expandButton.textContent = "Volver a vista normal";
    scene.request();
    save();
  }
  button("Crear concepto aquí", () => start("create"), toolbar, true);
  const selection = selector(
    toolbar,
    "Seleccionar concepto",
    [
      { value: "", text: "Buscar o seleccionar concepto" },
      ...data.nodes.map((n) => ({
        value: n.key,
        text: `${n.titulo} · ${n.source}`,
      })),
    ],
    view.selected,
    (key) => {
      if (key) select(key);
    },
  );
  field(toolbar, "Buscar nombre o ID", "", (query) => {
    view.auto = false;
    selection.replaceChildren();
    [{ key: "", titulo: "Buscar o seleccionar concepto" }, ...data.nodes]
      .filter(
        (n) =>
          !n.key ||
          (n.key + n.titulo)
            .toLocaleLowerCase()
            .includes(query.toLocaleLowerCase()),
      )
      .forEach((n) => selection.append(new Option(n.titulo, n.key)));
  });
  const plane = button(
    view.flat ? "Esfera S²" : "Plano",
    () => {
      view.flat = !view.flat;
      plane.textContent = view.flat ? "Esfera S²" : "Plano";
      refresh();
    },
    toolbar,
  );
  button(
    "Ajustar vista",
    () => {
      view.camera = { yaw: 0, pitch: 0, zoom: 1 };
      view.auto = false;
      redraw();
    },
    toolbar,
  );
  const expandButton = button("Expandir mapa", expand, toolbar);
  button(
    "Plegar ficha",
    () => {
      root.classList.toggle("card-hidden");
      scene.request();
    },
    toolbar,
  );
  const extras = element("details", "", "extra-actions");
  extras.append(element("summary", "Más acciones"));
  toolbar.append(extras);
  button(
    "− Zoom",
    () => {
      view.camera.zoom = Math.max(0.5, view.camera.zoom - 0.15);
      redraw();
    },
    extras,
  );
  button(
    "+ Zoom",
    () => {
      view.camera.zoom = Math.min(2.5, view.camera.zoom + 0.15);
      redraw();
    },
    extras,
  );
  const auto = button(
    "Giro suave",
    () => {
      view.selected = "";
      view.auto = !view.auto;
      auto.textContent = view.auto ? "Pausar giro" : "Giro suave";
      redraw();
    },
    extras,
  );
  button(
    "Deshacer reubicación",
    () => {
      scene.undoLayout();
      refresh();
    },
    extras,
  );
  button(
    "Restablecer disposición",
    () => {
      scene.rememberLayout();
      view.points = positions(
        data.nodes.map((n) => n.key),
        {},
      );
      view.flatPoints = {};
      view.layoutDirty = true;
      refresh();
    },
    extras,
  );
  field(extras, "Nombre de la vista", view.mapName, (value) => {
    view.mapName = value;
    save();
  });
  button(
    "Guardar disposición",
    () => {
      if (view.pending) return;
      view.pending = {
        operation_id: crypto.randomUUID(),
        action: "save_view",
        map_uid: view.mapUid,
        map_name: view.mapName,
        revision: view.viewRevision ?? "",
        view_state: studyState(view),
      };
      submitPending();
    },
    extras,
  );
  selector(
    extras,
    "Abrir vista guardada",
    [
      { value: "", text: "Elegir vista guardada" },
      ...(data.views ?? []).map((s) => ({ value: s.uid, text: s.name })),
    ],
    view.mapUid,
    (savedUid) => {
      const chosen = data.views?.find((s) => s.uid === savedUid);
      if (!chosen) return;
      closeEditor();
      view.draft = undefined;
      useSavedView(view, chosen);
      vault = new DraftVault(data.scope, chosen.uid);
      renderThemes();
      refresh();
    },
  );
  button(
    "Recuperar borradores",
    () => {
      const list = element("dialog", "", "document-dialog drafts-dialog");
      list.append(element("h2", "Borradores locales recuperables"));
      const drafts = vault.all();
      if (!drafts.length)
        list.append(
          element("p", "No hay borradores pendientes en esta vista."),
        );
      drafts.forEach((draft) =>
        button(
          `${draft.title || "Sin nombre"} · ${draft.action}`,
          () => {
            list.close();
            view.draft = draft;
            showEditor();
          },
          list,
        ),
      );
      button("Cerrar borradores", () => list.close(), list);
      list.onclose = () => list.remove();
      root.append(list);
      list.showModal();
    },
    extras,
  );
  const goalName = field(extras, "Pregunta o concepto pendiente", "", () => {});
  button(
    "Reservar pendiente aquí",
    () => {
      const label = goalName.value.trim();
      if (!label) return;
      view.goals!.push({
        id: crypto.randomUUID(),
        label,
        point: unit(unrotate([0.2, 0.15, 1], view.camera)),
        state: "pending",
        draftId: "",
        conceptKey: "",
      });
      view.layoutDirty = true;
      goalName.value = "";
      refresh();
    },
    extras,
  );
  renderFilters();
  renderThemes();
  renderAside();
  renderStatus();
  save();
  if (view.expanded) {
    view.expanded = false;
    expand();
  }
  if (view.draft) showEditor();
  const cleanup = () => {
    closeEditor();
    readingDispose?.();
    scene.destroy();
    if (timer) clearTimeout(timer);
    expansion?.remove();
    save();
  };
  mounted.set(parentElement, cleanup);
  return cleanup;
}
