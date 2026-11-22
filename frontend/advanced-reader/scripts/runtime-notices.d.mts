/** Build-only notice emitter; the directory override isolates filesystem tests. */
export function runtimeNotices(directory?: string): {
  name: string;
  generateBundle(this: { emitFile: (asset: { type: string; fileName: string; source: string }) => unknown }): void;
};
