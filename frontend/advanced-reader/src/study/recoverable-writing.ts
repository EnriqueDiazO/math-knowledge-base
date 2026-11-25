/** Read the existing library-scoped draft stores. This index never writes or claims a draft. */
import { studyVault, type StudyDraft } from "./drafts";
import { diaryChanges } from "./notebook-state";
export type RecoverableWriting = {
  key: string;
  title: string;
  path: string;
  kind: string;
};
export function recoverableWriting(library: string): RecoverableWriting[] {
  const items = (studyVault(library).all() as StudyDraft[])
    .filter((d) => d.title || d.content || d.pending)
    .map((d) => ({
      key: d.id!,
      title: d.title || "Nota sin título",
      path: "/study/write?draft=" + encodeURIComponent(d.id!),
      kind: d.noteId ? "Copia local de nota guardada" : "Nota sin publicar",
    }));
  const groups = [
    ["mathmongo-diary-v1-" + library + "-", "/study/notebook/", "Diario"],
    [
      "mathmongo-structured-v1-" + library + "-cornell-",
      "/study/notebook/cornell/",
      "Cornell",
    ],
    [
      "mathmongo-structured-v1-" + library + "-cpi-",
      "/study/notebook/cpi/",
      "CPI",
    ],
  ];
  try {
    for (let index = 0; index < localStorage.length; index++) {
      const key = localStorage.key(index)!;
      if (/-archive-[\da-f-]{36}$/iu.test(key)) continue;
      const group = groups.find(([prefix]) => key.startsWith(prefix));
      if (!group) continue;
      const [prefix, path, kind] = group,
        identity = key.slice(prefix.length);
      let title = "Borrador por revisar";
      try {
        const draft = JSON.parse(localStorage.getItem(key)!),
          original = JSON.parse(draft.original || "{}");
        if (kind === "Diario") {
          if (!draft.pending && Object.keys(diaryChanges(draft)).length === 0)
            continue;
          title = draft.title || "Entrada sin título";
        } else {
          const metadata = JSON.parse(draft.metadata),
            document = JSON.parse(draft.document);
          if (
            !draft.pending &&
            JSON.stringify(metadata) === JSON.stringify(original.metadata) &&
            JSON.stringify(document) === JSON.stringify(original.document)
          )
            continue;
          title = metadata.title || "Nota sin título";
        }
      } catch {
        /* Keep an explicit recovery link; do not rewrite a corrupt archive. */
      }
      items.push({
        key,
        title,
        path: path + encodeURIComponent(identity),
        kind,
      });
    }
  } catch {
    /* Stored notes remain available when localStorage is denied. */
  }
  return items;
}
