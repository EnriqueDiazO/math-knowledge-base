import { createRoot } from "react-dom/client";
import { lazy, Suspense } from 'react';

import { configureReaderTheme } from "./study-reader-theme";
import { StudyApp } from "./study/StudyApp";

configureReaderTheme(document.documentElement, location.search);

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("Advanced Reader root element is missing.");
}

const readerRoute = location.pathname === '/reader' || new URLSearchParams(location.search).has('document_id');
const ReaderEntry = lazy(() => import('./app/ReaderEntry'));
createRoot(rootElement).render(<Suspense fallback={<p role="status">Abriendo MathMongo…</p>}>{readerRoute ? <ReaderEntry /> : <StudyApp />}</Suspense>);
