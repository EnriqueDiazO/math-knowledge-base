/** Window ownership survives reload and separates sessionStorage copied by window.open. */
import { DraftVault } from "../knowledge-map/drafts";
const marker = "mathmongo-concept-window-v1";
type Ownership = { id: string; recoverable: boolean };
const owned = new Map<string, Promise<Ownership>>();

function windowOwnership() {
  let id: string;
  try {
    id = sessionStorage.getItem(marker) || crypto.randomUUID();
    sessionStorage.setItem(marker, id);
  } catch {
    id = crypto.randomUUID();
    return { initial: id, ready: Promise.resolve({ id, recoverable: false }) };
  }
  const existing = owned.get(id);
  if (existing) return { initial: id, ready: existing };
  if (!navigator.locks)
    return { initial: id, ready: Promise.resolve({ id, recoverable: false }) };
  const initial = id;
  let resolve!: (value: Ownership) => void;
  const ready = new Promise<Ownership>((done) => {
    resolve = done;
  });
  owned.set(initial, ready);
  const claim = (candidate: string) => {
    void navigator.locks
      .request(
        "mathmongo-concept-window-" + candidate,
        { ifAvailable: true },
        (lock) => {
          if (!lock) {
            claim(crypto.randomUUID());
            return;
          }
          try {
            sessionStorage.setItem(marker, candidate);
          } catch {
            resolve({ id: initial, recoverable: false });
            return;
          }
          owned.set(candidate, ready);
          resolve({ id: candidate, recoverable: true });
          // The browser releases this exclusive lock when this document is destroyed.
          // Keep it across SPA navigation; React component unmount is not window close.
          return new Promise<void>(() => {
            /* Window lifetime owns the lease. */
          });
        },
      )
      .catch(() => resolve({ id: initial, recoverable: false }));
  };
  claim(initial);
  return { initial, ready };
}

export function conceptDraftStorage(library: string) {
  const ownership = windowOwnership();
  const descriptor = {
    current: new DraftVault(
      library,
      "study-concepts-window-" + ownership.initial,
    ),
    legacy: new DraftVault(library, "study-concepts"),
    recoverable: false,
    ready: Promise.resolve(),
  };
  descriptor.ready = ownership.ready.then((window) => {
    if (window.id !== ownership.initial) {
      const previous = descriptor.current;
      descriptor.current = new DraftVault(
        library,
        "study-concepts-window-" + window.id,
      );
      // A cloned window keeps its own copy; the opener's archive is never modified.
      for (const draft of previous.all()) descriptor.current.put(draft);
    }
    descriptor.recoverable = window.recoverable && descriptor.current.available;
  });
  return descriptor;
}
