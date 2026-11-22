/** Browser history is the route authority; an unmounted view cannot accept old data. */
import { useEffect, useState } from "react";
import { studyRequest } from "./api";
import type { StudyContext } from "./api";

export type Navigate = (path: string, replace?: boolean) => void;
export function useStudyRoute() {
  const [route, setRoute] = useState(() => location.pathname + location.search);
  useEffect(() => {
    const update = () => setRoute(location.pathname + location.search);
    addEventListener("popstate", update);
    return () => removeEventListener("popstate", update);
  }, []);
  const navigate: Navigate = (path, replace = false) => {
    if (!path.startsWith("/study") || path.startsWith("//")) return;
    history[replace ? "replaceState" : "pushState"](null, "", path);
    dispatchEvent(new PopStateEvent("popstate"));
  };
  return { route, navigate };
}
export function useStudyResource<T>(context: StudyContext, path: string) {
  const key = context.library_id + ":" + context.runtime_id + path;
  const [state, setState] = useState<{ key: string; data?: T; error?: string }>(
    { key: "" },
  );
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    studyRequest<T>(path, context, undefined, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ key, data });
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setState({ key, error: String(reason.message) });
      });
    return () => controller.abort();
  }, [key, context, path, retry]);
  return {
    data: state.key === key ? state.data : undefined,
    error: state.key === key ? state.error : undefined,
    retry: () => setRetry((value) => value + 1),
  };
}
