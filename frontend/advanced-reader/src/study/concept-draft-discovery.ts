/** Read-only discovery is independent from recovery presentation. */
import { DraftVault } from "../knowledge-map/drafts";
import type { Draft } from "../knowledge-map/model";
export function discoverConceptDrafts(
  library: string,
  current: string,
  id: string,
) {
  const prefix = "mathmongo-drafts-v2-" + library + "-study-concepts";
  const copies: { archive: string; draft: Draft }[] = [];
  let unavailable = false;
  try {
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index)!;
      if (
        key === current ||
        (key !== prefix && !key.startsWith(prefix + "-window-"))
      )
        continue;
      const map = key.slice(("mathmongo-drafts-v2-" + library + "-").length);
      const vault = new DraftVault(library, map);
      unavailable ||= !vault.available;
      const draft = vault.get(id);
      if (
        draft &&
        !draft.completed &&
        ["edit", "create"].includes(draft.action)
      )
        copies.push({ archive: key, draft });
    }
  } catch {
    unavailable = true;
  }
  return {
    copies: copies.sort(
      (a, b) => (b.draft.updated ?? 0) - (a.draft.updated ?? 0),
    ),
    unavailable,
  };
}

