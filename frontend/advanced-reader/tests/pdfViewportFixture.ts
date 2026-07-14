import type { PdfJsViewport } from "../src/annotations/geometry";

type ViewBox = readonly [number, number, number, number];

/** A deterministic implementation of the public PDF.js PageViewport contract. */
export class PdfJsViewportFixture implements PdfJsViewport {
  readonly width: number;
  readonly height: number;
  readonly rotation: number;

  constructor(
    readonly viewBox: ViewBox = [10, 20, 610, 820],
    readonly scale = 1,
    rotation = 0,
  ) {
    this.rotation = ((rotation % 360) + 360) % 360;
    const pageWidth = viewBox[2] - viewBox[0];
    const pageHeight = viewBox[3] - viewBox[1];
    const quarterTurn = this.rotation === 90 || this.rotation === 270;
    this.width = (quarterTurn ? pageHeight : pageWidth) * scale;
    this.height = (quarterTurn ? pageWidth : pageHeight) * scale;
  }

  convertToViewportPoint(pdfX: number, pdfY: number): [number, number] {
    const [xMin, yMin, xMax, yMax] = this.viewBox;
    switch (this.rotation) {
      case 0:
        return [(pdfX - xMin) * this.scale, (yMax - pdfY) * this.scale];
      case 90:
        return [(pdfY - yMin) * this.scale, (pdfX - xMin) * this.scale];
      case 180:
        return [(xMax - pdfX) * this.scale, (pdfY - yMin) * this.scale];
      case 270:
        return [(yMax - pdfY) * this.scale, (xMax - pdfX) * this.scale];
      default:
        throw new RangeError("PDF.js only accepts quarter-turn rotations.");
    }
  }

  convertToPdfPoint(x: number, y: number): [number, number] {
    const [xMin, yMin, xMax, yMax] = this.viewBox;
    switch (this.rotation) {
      case 0:
        return [xMin + x / this.scale, yMax - y / this.scale];
      case 90:
        return [xMin + y / this.scale, yMin + x / this.scale];
      case 180:
        return [xMax - x / this.scale, yMin + y / this.scale];
      case 270:
        return [xMax - y / this.scale, yMax - x / this.scale];
      default:
        throw new RangeError("PDF.js only accepts quarter-turn rotations.");
    }
  }

  clone(parameters: { rotation?: number; scale?: number } = {}): PdfJsViewportFixture {
    return new PdfJsViewportFixture(
      this.viewBox,
      parameters.scale ?? this.scale,
      parameters.rotation ?? this.rotation,
    );
  }
}
