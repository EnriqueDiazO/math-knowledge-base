/** Study room: canonical resource references, explicit presentation saves, shared editor. */
import type { Bridge } from "./component";
import type { Draft, SavedView, Intent } from "./model";
import { freshView, draftFor } from "./model";
import { applyStudyTheme } from "./theme";
import { element, button, field, selector } from "./ui";
import { DraftVault } from "./drafts";
import {
  RoomVault,
  emptyRoom,
  fromSavedRoom,
  memberKeys,
  sharedConcepts,
  noteDraft,
  roomPose,
  acceptRoomResult,
} from "./room-state";
import type { Workspace } from "./room-state";
const vaults = new Map<string, RoomVault>();
export function renderRoom(
  bridge: Bridge,
  renderMap: (bridge: Bridge) => () => void,
): () => void {
  const { data, parentElement, setTriggerValue } = bridge;
  let vault = vaults.get(data.scope);
  if (!vault) {
    vault = new RoomVault(data.scope, data.rooms?.[0]);
    vaults.set(data.scope, vault);
  }
  let room = vault.current();
  if (acceptRoomResult(room, data.result)) vault.save();
  const root = element("section", "", "knowledge-map study-room");
  root.setAttribute("aria-label", "Habitación de estudio");
  applyStudyTheme(root);
  const host =
    parentElement.querySelector(".knowledge-map-root") ?? parentElement;
  host.replaceChildren(root);
  let children: (() => void)[] = [];
  let disposed = false;
  const persist = () => vault!.save();
  const dirty = () => {
    room.dirty = true;
    persist();
  };
  const viewScope = (uid: string) => data.scope + ":view:" + uid;
  const noteScope = () => data.scope + ":notes:" + room.uid;
  const noteVault = () => new DraftVault(noteScope(), room.uid);
  const namedView = (uid: string) => data.views?.find((v) => v.uid === uid);
  const renderLater = () =>
    queueMicrotask(() => {
      if (!disposed) render();
    });
  const mode = (value: Workspace["mode"]) => {
    room.mode = value;
    persist();
    render();
  };
  const request = (intent: Intent) => {
    if (room.pending) return;
    room.pending = intent;
    persist();
    setTriggerValue("intent", intent);
    render();
  };
  const openNote = (draft?: Draft) => {
    const entry = draft ?? noteDraft(data, room);
    entry.id ??= crypto.randomUUID();
    room.noteDraft = entry.id;
    noteVault().put(entry);
    mode("note");
  };
  const openViewDraft = (view: SavedView, draft: Draft) => {
    draft.id ??= crypto.randomUUID();
    new DraftVault(viewScope(view.uid), view.uid).put(draft);
    room.noteDraft = draft.id;
    room.draftView = view.uid;
    room.focus = view.uid;
    mode("focus");
  };
  const focus = (uid: string, selected = "") => {
    room.focus = uid;
    room.selected = selected;
    mode("focus");
  };
  function leaf(parent: HTMLElement, view: SavedView, expanded: boolean): void {
    const entry =
      room.draftView === view.uid && room.noteDraft
        ? new DraftVault(viewScope(view.uid), view.uid).get(room.noteDraft)
        : undefined;
    children.push(
      renderMap({
        ...bridge,
        parentElement: parent,
        data: { ...data, scope: viewScope(view.uid), roomMode: false },
        initialView: view,
        initialDraft: entry && !entry.completed ? entry : undefined,
        expandOnMount: expanded,
        selectionKey: room.selected || undefined,
        onExit: expanded ? () => mode("general") : undefined,
        onSelect: (key) => {
          if (room.mode === "compare" && room.selected !== key) {
            room.selected = key;
            persist();
            renderLater();
          }
        },
        onSaved: (result, draft) => {
          if (result.status === "saved" && draft.action === "publish_note") {
            room.result = {
              ...result,
              message:
                "Concepto incorporado; guarda la disposición para confirmar su pertenencia a esta esfera.",
            };
            room.noteDraft = undefined;
            room.draftView = undefined;
            persist();
          }
        },
      }),
    );
  }
  function renderHeader(): void {
    const header = element("header", "", "room-heading");
    header.append(element("h2", room.state.name));
    button("General", () => mode("general"), header).setAttribute(
      "aria-pressed",
      String(room.mode === "general"),
    );
    button("Comparar", () => mode("compare"), header).disabled =
      room.state.spheres.length < 2;
    button(
      "Guardar habitación",
      () =>
        request({
          operation_id: crypto.randomUUID(),
          action: "save_room",
          room_uid: room.uid,
          revision: room.revision,
          room_state: structuredClone(room.state),
        }),
      header,
      true,
    ).disabled = !!room.pending;
    header.append(
      element(
        "span",
        room.pending
          ? "Envío pendiente de confirmar"
          : room.dirty
            ? "Disposición local sin guardar"
            : room.revision
              ? "Disposición guardada"
              : "Habitación local; aún no guardada",
        "hint",
      ),
    );
    root.append(header);
    if (vault!.error) root.append(element("p", vault!.error, "room-warning"));
    if (room.result) {
      const message = element("p", room.result.message, "room-message");
      message.setAttribute("role", "status");
      root.append(message);
    }
    if (room.pending)
      button(
        "Reconciliar el mismo envío",
        () => setTriggerValue("intent", room.pending),
        root,
      );
    if (room.result?.status === "conflict") {
      const current = data.rooms?.find((r) => r.uid === room.uid);
      if (current) {
        const details = element("details");
        details.append(
          element("summary", "Revisar habitación guardada"),
          element("pre", JSON.stringify(current.state, null, 2)),
        );
        button(
          "He revisado: conservar mi disposición y adoptar esta revisión",
          () => {
            room.revision = current.revision;
            room.result = undefined;
            persist();
            render();
          },
          details,
        );
        root.append(details);
      }
    }
  }
  function renderCollection(): void {
    const settings = element("details");
    settings.append(element("summary", "Habitaciones y colección de esferas"));
    field(settings, "Nombre de la habitación", room.state.name, (value) => {
      room.state.name = value;
      dirty();
    });
    selector(
      settings,
      "Abrir habitación",
      [
        { value: "", text: "Elegir habitación" },
        ...[
          ...new Set([
            ...vault!.all().map((r) => r.uid),
            ...(data.rooms ?? []).map((r) => r.uid),
          ]),
        ].map((uid) => ({
          value: uid,
          text:
            vault!.get(uid)?.state.name ??
            data.rooms!.find((r) => r.uid === uid)!.state.name,
        })),
      ],
      room.uid,
      (uid) => {
        const saved = data.rooms?.find((r) => r.uid === uid);
        const next =
          vault!.get(uid) ?? (saved ? fromSavedRoom(saved) : undefined);
        if (next) {
          persist();
          vault!.select(next);
          room = next;
          render();
        }
      },
    );
    button(
      "Nueva habitación local",
      () => {
        persist();
        room = emptyRoom();
        vault!.select(room);
        render();
      },
      settings,
    );
    let selectedView = "";
    selector(
      settings,
      "Añadir una vista guardada",
      [
        { value: "", text: "Elegir esfera" },
        ...(data.views ?? []).map((v) => ({ value: v.uid, text: v.name })),
      ],
      "",
      (value) => {
        selectedView = value;
      },
    );
    button(
      "Añadir esta esfera a la habitación",
      () => {
        if (
          !namedView(selectedView) ||
          room.state.spheres.some((v) => v.view_uid === selectedView)
        )
          return;
        room.state.spheres.push({
          view_uid: selectedView,
          position: roomPose(
            0.25 + ((room.state.spheres.length * 0.3) % 0.6),
            0.45,
          ),
        });
        dirty();
        render();
      },
      settings,
    );
    const name = field(
      settings,
      "Nombre de una nueva esfera vacía",
      "Nueva esfera",
      () => {},
    );
    button(
      "Crear y guardar esfera vacía",
      () => {
        if (!name.value.trim()) return;
        request({
          operation_id: crypto.randomUUID(),
          action: "save_view",
          map_uid: crypto.randomUUID(),
          map_name: name.value.trim(),
          revision: "",
          view_state: {
            version: 1,
            points: {},
            flatPoints: {},
            pinned: [],
            areas: [],
            goals: [],
            mandala: false,
            members: [],
          },
        });
      },
      settings,
    ).disabled = !!room.pending;
    button(
      "Descargar disposición local",
      () => {
        const url = URL.createObjectURL(
          new Blob([JSON.stringify(room, null, 2)], {
            type: "application/json",
          }),
        );
        const link = element("a");
        link.href = url;
        link.download = "mathmongo-habitacion.json";
        link.click();
        URL.revokeObjectURL(url);
      },
      settings,
    );
    root.append(settings);
  }
  function renderStage(): void {
    const stage = element("section", "", "room-stage");
    stage.setAttribute("aria-label", "Organización espacial de las esferas");
    if (!room.state.spheres.length)
      stage.append(
        element(
          "p",
          "Añade una vista guardada o crea una esfera vacía. Los recursos reales aparecen debajo.",
        ),
      );
    room.state.spheres.forEach((reference, index) => {
      const view = namedView(reference.view_uid);
      const card = element("article", "", "room-sphere");
      card.dataset.viewUid = reference.view_uid;
      const position = () => {
        card.style.left = `${reference.position[0] * 100}%`;
        card.style.top = `${reference.position[1] * 100}%`;
        const line = stage.querySelector<SVGLineElement>(
          ".room-shared-line line",
        );
        if (line) {
          const left = room.state.spheres.find(
              (s) => s.view_uid === line.dataset.left,
            ),
            right = room.state.spheres.find(
              (s) => s.view_uid === line.dataset.right,
            );
          if (left && right) {
            line.setAttribute("x1", String(left.position[0] * 100));
            line.setAttribute("y1", String(left.position[1] * 100));
            line.setAttribute("x2", String(right.position[0] * 100));
            line.setAttribute("y2", String(right.position[1] * 100));
          }
        }
      };
      position();
      button(
        view?.name ?? "Vista no disponible",
        () => {
          if (view) focus(view.uid);
        },
        card,
        true,
      ).title = view?.name ?? reference.view_uid;
      card.append(
        element(
          "p",
          view
            ? `${memberKeys(data, view).size} conceptos · ${view.state.areas.join(", ") || "sin áreas elegidas"}`
            : "La referencia se conserva para revisión",
        ),
      );
      const handle = button("Recolocar esfera " + (index + 1), () => {}, card);
      handle.setAttribute(
        "aria-label",
        "Recolocar " + (view?.name ?? reference.view_uid),
      );
      let start: [number, number] | undefined;
      handle.onpointerdown = (event) => {
        event.preventDefault();
        event.stopPropagation();
        start = [...reference.position];
        handle.setPointerCapture(event.pointerId);
      };
      handle.onpointermove = (event) => {
        if (!start || !handle.hasPointerCapture(event.pointerId)) return;
        const rect = stage.getBoundingClientRect();
        reference.position = roomPose(
          (event.clientX - rect.left) / rect.width,
          (event.clientY - rect.top) / rect.height,
        );
        position();
      };
      handle.onpointerup = (event) => {
        if (!start) return;
        handle.releasePointerCapture(event.pointerId);
        start = undefined;
        dirty();
      };
      handle.onpointercancel = () => {
        if (start) reference.position = start;
        start = undefined;
        position();
      };
      handle.onkeydown = (event) => {
        const deltas: Record<string, [number, number]> = {
          ArrowLeft: [-0.025, 0],
          ArrowRight: [0.025, 0],
          ArrowUp: [0, -0.025],
          ArrowDown: [0, 0.025],
        };
        if (deltas[event.key]) {
          event.preventDefault();
          const d = deltas[event.key];
          reference.position = roomPose(
            reference.position[0] + d[0],
            reference.position[1] + d[1],
          );
          position();
          dirty();
        }
      };
      button(
        "Quitar referencia a esta esfera",
        () => {
          room.state.spheres = room.state.spheres.filter(
            (s) => s !== reference,
          );
          dirty();
          render();
        },
        card,
      );
      stage.append(card);
    });
    const document = data.documents?.find(
      (d) => d.document_id === room.state.document_id,
    );
    const book = button(
      document?.title ?? "Elegir fuente en la biblioteca",
      () => {
        if (document)
          setTriggerValue("open_source", { document_id: document.document_id });
        else setTriggerValue("open_library", {});
      },
      stage,
    );
    book.className = "room-book";
    book.title = document?.title ?? "Biblioteca";
    book.setAttribute("aria-label", "Abrir libro de estudio");
    const note = data.notes?.find((n) => n.note_id === room.state.note_id);
    const writing = room.noteDraft
      ? noteVault().get(room.noteDraft)
      : undefined;
    const paper = button(
      writing && !writing.completed
        ? writing.title || "Continuar borrador"
        : (note?.title ?? "Escribir una nota de trabajo"),
      () => {
        if (writing && !writing.completed) openNote(writing);
        else {
          room.noteDraft = undefined;
          openNote();
        }
      },
      stage,
    );
    paper.className = "room-paper";
    paper.setAttribute("aria-label", "Abrir papel de trabajo");
    const lamp = element("div", "", "room-lamp");
    lamp.setAttribute("aria-hidden", "true");
    stage.append(lamp);
    const views = pair();
    const shared = sharedConcepts(data, views[0], views[1]);
    if (shared.length) {
      const ns = "http://www.w3.org/2000/svg";
      const svg = root.ownerDocument.createElementNS(ns, "svg");
      svg.setAttribute("viewBox", "0 0 100 100");
      svg.setAttribute("preserveAspectRatio", "none");
      svg.classList.add("room-shared-line");
      svg.setAttribute("aria-hidden", "true");
      const line = root.ownerDocument.createElementNS(ns, "line");
      const first = room.state.spheres.find(
          (s) => s.view_uid === views[0].uid,
        )!,
        second = room.state.spheres.find((s) => s.view_uid === views[1].uid)!;
      line.dataset.left = first.view_uid;
      line.dataset.right = second.view_uid;
      line.setAttribute("x1", String(first.position[0] * 100));
      line.setAttribute("y1", String(first.position[1] * 100));
      line.setAttribute("x2", String(second.position[0] * 100));
      line.setAttribute("y2", String(second.position[1] * 100));
      svg.append(line);
      stage.prepend(svg);
    }
    root.append(stage);
    renderShared();
  }
  function pair(): SavedView[] {
    const available = room.state.spheres
      .map((s) => namedView(s.view_uid))
      .filter((v): v is SavedView => !!v);
    const chosen = room.comparison
      .map((uid) => available.find((v) => v.uid === uid))
      .filter((v): v is SavedView => !!v);
    for (const view of available)
      if (chosen.length < 2 && !chosen.some((v) => v.uid === view.uid))
        chosen.push(view);
    room.comparison = chosen.map((v) => v.uid);
    return chosen.slice(0, 2);
  }
  function renderShared(): void {
    const views = pair();
    const shared = sharedConcepts(data, views[0], views[1]);
    const details = element("details");
    details.append(
      element(
        "summary",
        `${shared.length} conceptos compartidos entre las dos vistas elegidas`,
      ),
    );
    details.append(
      element(
        "p",
        "Compartir un ID representa pertenencia a ambas vistas, no una relación matemática nueva. La posición no crea vínculos.",
      ),
    );
    shared.forEach((key) => {
      const node = data.nodes.find((n) => n.key === key)!;
      button(
        `${node.titulo} · ${node.source} · ${node.id}`,
        () => {
          room.selected = key;
          mode("compare");
        },
        details,
      );
    });
    root.append(details);
  }
  function renderCompare(): void {
    const views = pair();
    if (views.length < 2) {
      root.append(
        element("p", "Añade al menos dos vistas guardadas para comparar."),
      );
      return;
    }
    const controls = element("div", "", "room-compare-selectors");
    for (let index = 0; index < 2; index++)
      selector(
        controls,
        `Esfera ${index + 1} para comparar`,
        room.state.spheres.map((s) => ({
          value: s.view_uid,
          text: namedView(s.view_uid)?.name ?? s.view_uid,
        })),
        views[index].uid,
        (uid) => {
          const other = room.comparison[1 - index];
          room.comparison[index] = uid;
          if (uid === other) room.comparison[1 - index] = views[index].uid;
          persist();
          render();
        },
      );
    views.forEach((v, index) =>
      button(
        "Mostrar " + v.name,
        () => {
          room.activePane = index;
          persist();
          render();
        },
        controls,
      ).setAttribute("aria-pressed", String(room.activePane === index)),
    );
    root.append(controls);
    renderShared();
    const comparison = element("div", "", "room-comparison");
    root.append(comparison);
    views.forEach((view, index) => {
      const pane = element("section", "", "room-compare-pane");
      pane.dataset.active = String(room.activePane === index);
      pane.append(element("h3", view.name));
      button("Enfocar " + view.name, () => focus(view.uid), pane);
      const map = element("div");
      pane.append(map);
      comparison.append(pane);
      leaf(map, view, false);
    });
  }
  function sourcePanel(): HTMLElement {
    const sources = element("article", "", "room-resource-card");
    sources.append(element("h3", "Fuentes de estudio"));
    selector(
      sources,
      "Fuente o documento de lectura",
      [
        { value: "", text: "Elegir documento" },
        ...(data.documents ?? []).map((d) => ({
          value: d.document_id,
          text: d.title,
        })),
      ],
      room.state.document_id,
      (value) => {
        room.state.document_id = value;
        room.state.note_id = "";
        room.annotation = "";
        dirty();
        render();
      },
    );
    const document = data.documents?.find(
      (d) => d.document_id === room.state.document_id,
    );
    button(
      "Abrir fuente en el lector",
      () =>
        setTriggerValue("open_source", { document_id: document!.document_id }),
      sources,
    ).disabled = !document;
    button(
      "Gestionar fuentes y referencias",
      () => setTriggerValue("open_library", {}),
      sources,
    );
    const marks = (data.annotations ?? []).filter(
      (a) => a.document_id === document?.document_id,
    );
    selector(
      sources,
      "Anotación o pasaje registrado",
      [
        { value: "", text: "Sin pasaje específico" },
        ...marks.map((a) => ({
          value: a.annotation_id,
          text: (a.quote_text ?? a.body).slice(0, 140),
        })),
      ],
      room.annotation,
      (value) => {
        room.annotation = value;
        persist();
        render();
      },
    );
    const mark = marks.find((a) => a.annotation_id === room.annotation);
    if (mark) {
      sources.append(element("blockquote", mark.quote_text ?? mark.body));
      button(
        "Volver al pasaje exacto",
        () =>
          setTriggerValue("open_source", {
            document_id: mark.document_id,
            annotation_id: mark.annotation_id,
          }),
        sources,
      );
    }
    button(
      mark ? "Escribir nota desde este pasaje" : "Escribir nota personal",
      () => {
        room.state.note_id = "";
        room.noteDraft = undefined;
        openNote();
      },
      sources,
    );
    return sources;
  }
  function notePanel(): HTMLElement {
    const notes = element("article", "", "room-resource-card");
    notes.append(element("h3", "Notas de trabajo"));
    selector(
      notes,
      "Nota personal",
      [
        { value: "", text: "Elegir nota" },
        ...(data.notes ?? []).map((n) => ({ value: n.note_id, text: n.title })),
      ],
      room.state.note_id,
      (value) => {
        room.state.note_id = value;
        room.noteDraft = undefined;
        dirty();
        render();
      },
    );
    const note = data.notes?.find((n) => n.note_id === room.state.note_id);
    button(
      "Abrir nota en el editor",
      () => {
        room.noteDraft = undefined;
        openNote();
      },
      notes,
    ).disabled = !note;
    if (note) {
      notes.append(
        element(
          "p",
          "Nota personal conservada; publicar requiere otra acción.",
        ),
      );
      if (note.document_id)
        button(
          "Abrir fuente de esta nota",
          () =>
            setTriggerValue("open_source", {
              document_id: note.document_id,
              note_id: note.note_id,
            }),
          notes,
        );
      const destination = namedView(room.focus) ?? pair()[0];
      selector(
        notes,
        "Esfera de destino para concepto",
        [
          { value: "", text: "Elegir esfera" },
          ...room.state.spheres.map((s) => ({
            value: s.view_uid,
            text: namedView(s.view_uid)?.name ?? s.view_uid,
          })),
        ],
        destination?.uid ?? "",
        (uid) => {
          room.focus = uid;
          persist();
          render();
        },
      );
      if (destination) {
        selector(
          notes,
          "Pregunta que completa esta nota (opcional)",
          [
            { value: "", text: "Sin pendiente asociado" },
            ...destination.state.goals
              .filter((g) => !g.conceptKey)
              .map((g) => ({ value: g.id, text: g.label })),
          ],
          room.state.goal_view_uid === destination.uid
            ? room.state.goal_id
            : "",
          (value) => {
            room.state.goal_view_uid = value ? destination.uid : "";
            room.state.goal_id = value;
            dirty();
          },
        );
      }
      button(
        "Incorporar nota como concepto…",
        () => {
          const view = namedView(room.focus) ?? destination;
          if (!view) return;
          const draft = noteDraft(data, room);
          draft.action = "publish_note";
          draft.noteRevision = note.revision;
          const goal =
            room.state.goal_view_uid === view.uid
              ? view.state.goals.find(
                  (g) => g.id === room.state.goal_id && !g.conceptKey,
                )
              : undefined;
          if (goal) {
            draft.goalId = goal.id;
            draft.point = structuredClone(goal.point);
          }
          draft.id = crypto.randomUUID();
          openViewDraft(view, draft);
        },
        notes,
      ).disabled = !destination;
    }
    const drafts = noteVault().all();
    if (drafts.length) {
      notes.append(element("h4", "Borradores locales recuperables"));
      drafts.forEach((d) =>
        button(
          d.title || "Nota sin título",
          () => {
            room.noteDraft = d.id;
            openNote(d);
          },
          notes,
        ),
      );
    }
    return notes;
  }
  function goalPanel(): HTMLElement {
    const goals = element("article", "", "room-resource-card");
    goals.append(element("h3", "Preguntas y pendientes"));
    for (const reference of room.state.spheres) {
      const view = namedView(reference.view_uid);
      if (!view) continue;
      for (const goal of view.state.goals)
        button(
          `${goal.label} · ${goal.state} · ${view.name}`,
          () => {
            if (goal.conceptKey) {
              focus(view.uid, goal.conceptKey);
              return;
            }
            const draft = draftFor(data, freshView(), "create", goal.point);
            draft.id = goal.draftId || crypto.randomUUID();
            draft.title = goal.label;
            draft.goalId = goal.id;
            openViewDraft(view, draft);
          },
          goals,
        );
    }
    if (!goals.querySelector("button"))
      goals.append(
        element(
          "p",
          "Reserva una pregunta dentro de una esfera. Los estados los eliges tú; no son porcentajes de comprensión.",
        ),
      );
    return goals;
  }
  function renderResources(): void {
    const resources = element("section", "", "room-resources");
    resources.append(sourcePanel(), notePanel(), goalPanel());
    root.append(resources);
    if (data.resource_limit)
      root.append(element("p", data.resource_limit, "hint"));
  }
  function renderNote(): void {
    const container = element("div", "", "room-note-workspace");
    root.append(container);
    const initial = noteDraft(data, room);
    children.push(
      renderMap({
        ...bridge,
        parentElement: container,
        data: { ...data, scope: noteScope(), roomMode: false },
        draftMapUid: room.uid,
        initialDraft: initial,
        expandOnMount: false,
        onExit: () => mode("general"),
        onSaved: (result) => {
          if (result.status !== "saved") return;
          if (result.note_id) {
            room.state.note_id = result.note_id;
            room.noteDraft = undefined;
            room.dirty = true;
          }
          room.result = result;
          room.mode = "general";
          persist();
          renderLater();
        },
      }),
    );
  }
  function render(): void {
    children.forEach((dispose) => dispose());
    children = [];
    root.replaceChildren();
    renderHeader();
    if (room.mode === "focus") {
      const view = namedView(room.focus);
      if (view) {
        const pane = element("div");
        root.append(pane);
        leaf(pane, view, true);
        return;
      }
      room.mode = "general";
    }
    if (room.mode === "compare") {
      renderCompare();
      return;
    }
    renderCollection();
    renderStage();
    renderResources();
    if (room.mode === "note") renderNote();
  }
  render();
  return () => {
    disposed = true;
    children.forEach((dispose) => dispose());
    persist();
  };
}
