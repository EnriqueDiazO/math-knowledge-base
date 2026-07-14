import { createRoot } from "react-dom/client";
import "pdfjs-dist/web/pdf_viewer.css";

import { AdvancedReaderApp } from "./app/App";
import { createPdfJsController } from "./pdf/PdfJsController";
import "./styles/reader.css";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("Advanced Reader root element is missing.");
}

createRoot(rootElement).render(<AdvancedReaderApp controllerFactory={createPdfJsController} />);
