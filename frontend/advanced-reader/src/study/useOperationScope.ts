import { useEffect, useMemo } from "react";
import type { StudyContext } from "./api";

/** An old response may reconcile only its own mounted library and runtime. */
export function useOperationScope(
  context: Pick<StudyContext, "library_id" | "runtime_id"> | undefined,
) {
  const library = context?.library_id ?? "",
    runtime = context?.runtime_id ?? "";
  const scope = useMemo(
    () => ({ active: true, library, runtime }),
    [library, runtime],
  );
  useEffect(() => {
    scope.active = true;
    return () => {
      scope.active = false;
    };
  }, [scope]);
  return scope;
}
