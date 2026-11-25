/** Keep existing local drafts readable and move a draft to IndexedDB on write failure. */
const databaseName = "mathmongo-diary-drafts";
const drafts = "drafts";
const titles = "titles";

export const diaryDraftPrefix = (library: string) =>
  "mathmongo-diary-v1-" + library + "-";

export type DiaryRestoration = { raw: string | null; inDatabase: boolean };
type BackupTitle = { key: string; title: string | null };
type Archive = { key: string; raw: string };

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, 1);
    let blocked = false;
    request.onupgradeneeded = () => {
      request.result.createObjectStore(drafts);
      request.result.createObjectStore(titles, { keyPath: "key" });
    };
    request.onblocked = () => {
      blocked = true;
      reject(new Error("Diary draft database is blocked"));
    };
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      if (blocked) request.result.close();
      else resolve(request.result);
    };
  });
}

async function transact<T = void>(
  stores: string | string[],
  mode: IDBTransactionMode,
  start: (transaction: IDBTransaction) => IDBRequest<T> | void,
): Promise<T> {
  const database = await openDatabase();
  try {
    return await new Promise<T>((resolve, reject) => {
      const transaction = database.transaction(stores, mode);
      const request = start(transaction);
      transaction.oncomplete = () => resolve(request?.result as T);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally {
    database.close();
  }
}

export function readLocalDiary(key: string): DiaryRestoration {
  try {
    return { raw: localStorage.getItem(key), inDatabase: false };
  } catch {
    return { raw: null, inDatabase: false };
  }
}

export async function restoreDiary(key: string): Promise<DiaryRestoration> {
  try {
    const raw = await transact<string | null | undefined>(
      drafts,
      "readonly",
      (tx) => tx.objectStore(drafts).get(key),
    );
    // A null record covers a confirmed creation whose legacy copy could not be removed.
    if (raw !== undefined) return { raw, inDatabase: true };
  } catch {
    /* IndexedDB is optional until localStorage fails. */
  }
  return readLocalDiary(key);
}

export async function diaryBackupTitles(library: string): Promise<BackupTitle[]> {
  const prefix = diaryDraftPrefix(library);
  try {
    return await transact<BackupTitle[]>(titles, "readonly", (tx) =>
      tx.objectStore(titles).getAll(IDBKeyRange.bound(prefix, prefix + "\uffff")),
    );
  } catch {
    return [];
  }
}

export function diaryStorage(key: string, restored: DiaryRestoration) {
  let inDatabase = restored.inDatabase;
  let queue: Promise<boolean> | undefined;
  const localWrite = (raw: string | null, archive?: Archive) => {
    try {
      if (archive) localStorage.setItem(archive.key, archive.raw);
      if (raw === null) localStorage.removeItem(key);
      else localStorage.setItem(key, raw);
      return true;
    } catch {
      return false;
    }
  };
  return {
    write(raw: string | null, title: string | null, archive?: Archive) {
      const previous = queue;
      if (!previous && !inDatabase && localWrite(raw, archive))
        return Promise.resolve(true);

      // Finish earlier writes first, including a move from localStorage to IndexedDB.
      const current = (previous ?? Promise.resolve()).then(async () => {
        if (previous && !inDatabase && localWrite(raw, archive)) return true;
        try {
          const remove = raw === null && localWrite(null);
          await transact([drafts, titles], "readwrite", (tx) => {
            const store = tx.objectStore(drafts),
              index = tx.objectStore(titles);
            if (remove) {
              store.delete(key);
              index.delete(key);
            } else {
              if (archive) store.put(archive.raw, archive.key);
              store.put(raw, key);
              index.put({ key, title });
            }
          });
          inDatabase = !remove;
          return true;
        } catch {
          return false;
        }
      });
      queue = current;
      void current.then(() => {
        if (queue === current) queue = undefined;
      });
      return current;
    },
  };
}
