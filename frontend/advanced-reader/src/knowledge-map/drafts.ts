import type { Draft, View } from "./model";
/** Browser-local draft recovery, isolated by connection/database and map identity. */
export class DraftVault {
  readonly key: string;
  private drafts: Record<string, Draft> = {};
  private unreadableArchive = false;
  available = true;
  constructor(scope: string, map: string) {
    this.key = "mathmongo-drafts-v2-" + scope + "-" + map;
    try {
      const parsed: unknown = JSON.parse(
        localStorage.getItem(this.key) ?? "{}",
      );
      if (
        !parsed ||
        typeof parsed !== "object" ||
        Array.isArray(parsed) ||
        Object.values(parsed).some(
          (value) =>
            !value ||
            typeof value !== "object" ||
            ![
              "create",
              "create_connected",
              "connect",
              "edit",
              "save_note",
              "publish_note",
            ].includes(value.action) ||
            typeof value.content !== "string" ||
            typeof value.title !== "string",
        )
      )
        throw new Error("Unreadable draft archive");
      this.drafts = parsed as Record<string, Draft>;
    } catch {
      this.available = false;
      this.unreadableArchive = true;
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
    if (this.unreadableArchive) return; // Preserve the original archive for recovery.
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
    if (this.unreadableArchive) return;
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
