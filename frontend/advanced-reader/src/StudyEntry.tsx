import { lazy, Suspense } from "react";
import { StudyApp } from "./study/StudyApp";

const ReaderEntry = lazy(() => import("./app/ReaderEntry"));
export function StudyEntry() {
  const readerRoute =
    location.pathname === "/reader" ||
    new URLSearchParams(location.search).has("document_id");
  return (
    <Suspense fallback={<p role="status">Abriendo MathMongo…</p>}>
      {readerRoute ? <ReaderEntry /> : <StudyApp />}
    </Suspense>
  );
}
