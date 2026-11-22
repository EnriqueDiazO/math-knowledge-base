import { createRoot } from "react-dom/client";

import { configureReaderTheme } from "./study-reader-theme";
import { StudyEntry } from "./StudyEntry";

configureReaderTheme(document.documentElement, location.search);

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("Advanced Reader root element is missing.");
}

createRoot(rootElement).render(<StudyEntry />);
