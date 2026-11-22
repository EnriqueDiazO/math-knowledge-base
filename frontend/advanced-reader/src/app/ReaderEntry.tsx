/** Share the real PDF controller; load its runtime only when entering reading. */
import "pdfjs-dist/web/pdf_viewer.css";
import "../styles/reader.css";
import "../styles/study-reader-theme.css";
import { AdvancedReaderApp } from "./App";
import type { AdvancedReaderAppProps } from "./App";
import { createPdfJsController } from "../pdf/PdfJsController";

export default function ReaderEntry(
  props: Omit<AdvancedReaderAppProps, "controllerFactory">,
) {
  return (
    <AdvancedReaderApp {...props} controllerFactory={createPdfJsController} />
  );
}
