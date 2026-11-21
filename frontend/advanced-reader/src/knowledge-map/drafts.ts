import type { Draft, View } from "./model";
/** Browser-local draft recovery, isolated by connection/database and map identity. */
export class DraftVault {
  readonly key: string;
  private drafts: Record<string, Draft> = {};
  available = true;
  constructor(scope: string, map: string) {
    this.key = "mathmongo-drafts-v2-" + scope + "-" + map;
    try {
      this.drafts = JSON.parse(
        localStorage.getItem(this.key) ?? "{}",
      ) as Record<string, Draft>;
    } catch {
      this.available = false;
    }
  }
  all(): Draft[] {
    return Object.values(this.drafts)
      .filter((d) => !d.completed)
      .sort((a, b) => (b.updated ?? 0) - (a.updated ?? 0));
  }
  put(draft: Draft): void {
    draft.id ??= crypto.randomUUID();
    draft.updated = Date.now();
    this.drafts[draft.id] = structuredClone(draft);
    try {
      localStorage.setItem(this.key, JSON.stringify(this.drafts));
      this.available = true;
    } catch {
      this.available = false;
    }
  }
  get(id: string): Draft | undefined {
    const value = this.drafts[id];
    return value ? structuredClone(value) : undefined;
  }
  discard(id: string): void {
    delete this.drafts[id];
    try {
      localStorage.setItem(this.key, JSON.stringify(this.drafts));
    } catch {
      this.available = false;
    }
  }
  complete(draft: Draft): void {
    this.put({ ...draft, completed: true });
  }
}
export function persistedView(scope: string): View | undefined {
  try {
    return JSON.parse(
      localStorage.getItem("mathmongo-map-v2-" + scope) ?? "null",
    ) as View | undefined;
  } catch {
    return;
  }
}
export function storeView(scope: string, view: View): boolean {
  try {
    localStorage.setItem("mathmongo-map-v2-" + scope, JSON.stringify(view));
    return true;
  } catch {
    return false;
  }
}
