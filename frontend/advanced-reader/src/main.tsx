import { createRoot } from "react-dom/client";
import "pdfjs-dist/web/pdf_viewer.css";

import { AdvancedReaderApp } from "./app/App";
import { createPdfJsController } from "./pdf/PdfJsController";
import "./styles/reader.css";
import "./styles/study-reader-theme.css";
import { configureReaderTheme } from "./study-reader-theme";

configureReaderTheme(document.documentElement, location.search);

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("Advanced Reader root element is missing.");
}

createRoot(rootElement).render(<AdvancedReaderApp controllerFactory={createPdfJsController} />);
