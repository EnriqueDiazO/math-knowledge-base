import { useEffect, useRef, useState } from "react";
import { downloadDocument } from "./api";
import {
  diaryStorage,
  readLocalDiary,
  restoreDiary,
  type DiaryRestoration,
} from "./diary-storage";
import { diaryChanges, type DiaryDraft } from "./notebook-state";

export function useDiaryRestoration(key: string) {
  const [restored, update] = useState<DiaryRestoration | null>(() =>
    "indexedDB" in globalThis ? null : readLocalDiary(key),
  );
  useEffect(() => {
    if (!("indexedDB" in globalThis)) return;
    let active = true;
    void restoreDiary(key).then((draft) => {
      if (!active) return;
      update(draft);
    });
    return () => {
      active = false;
    };
  }, [key]);
  return restored;
}

function readDraft(raw: string | null, initial: DiaryDraft) {
  if (raw === null) return { value: initial, corrupt: false };
  try {
    const parsed = JSON.parse(raw);
    if (
      !parsed ||
      typeof parsed !== "object" ||
      Array.isArray(parsed) ||
      Object.keys(initial).some((field) => typeof parsed[field] !== "string")
    )
      throw new Error("Invalid Diary draft");
    return { value: parsed as DiaryDraft, corrupt: false };
  } catch {
    return { value: initial, corrupt: true };
  }
}

function draftTitle(draft: DiaryDraft) {
  try {
    if (!draft.pending && Object.keys(diaryChanges(draft)).length === 0)
      return null;
    return draft.title || "Entrada sin título";
  } catch {
    return "Borrador por revisar";
  }
}

export function useDiaryForm(
  key: string,
  restored: DiaryRestoration,
  initial: () => DiaryDraft,
) {
  const [loaded] = useState(() => readDraft(restored.raw, initial()));
  const [store] = useState(() => diaryStorage(key, restored));
  const [state, update] = useState(loaded.value);
  const [corrupt, setCorrupt] = useState(loaded.corrupt);
  const [storageFailed, setStorageFailed] = useState(false);
  const current = useRef(loaded.value), version = useRef(0);

  const keep = (next: DiaryDraft) => {
    current.current = next;
    update(next);
  };
  const set = async (next: DiaryDraft) => {
    keep(next);
    const writing = ++version.current;
    const ok = await store.write(JSON.stringify(next), draftTitle(next));
    if (writing === version.current) setStorageFailed(!ok);
    return ok;
  };

  return {
    state,
    current,
    keep,
    set,
    storageFailed,
    problem: corrupt
      ? "El borrador anterior no se pudo leer y se conserva intacto. Descárgalo antes de reiniciar."
      : "",
    retry: () => set(current.current),
    clear: () => store.write(null, null),
    download: () => {
      const raw = corrupt
        ? restored.raw!
        : JSON.stringify(current.current, null, 2);
      downloadDocument(
        new Blob([raw], { type: "application/json" }),
        "mathmongo-borrador.json",
      );
    },
    restart: async (next: DiaryDraft) => {
      const ok = await store.write(JSON.stringify(next), null, {
        key: key + "-archive-" + crypto.randomUUID(),
        raw: restored.raw ?? JSON.stringify(current.current),
      });
      if (ok) {
        setCorrupt(false);
        setStorageFailed(false);
        keep(next);
      }
      return ok;
    },
  };
}
