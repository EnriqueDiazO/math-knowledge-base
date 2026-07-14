const MAX_AUDIT_EDGE = 160;
const WHITE_CHANNEL_THRESHOLD = 250;

export interface CanvasPaintInspection {
  width: number;
  height: number;
  sampledPixels: number;
  nonWhitePixels: number;
  minChannel: number;
  maxChannel: number;
  painted: boolean;
}

function emptyInspection(canvas: HTMLCanvasElement): CanvasPaintInspection {
  return {
    width: canvas.width,
    height: canvas.height,
    sampledPixels: 0,
    nonWhitePixels: 0,
    minChannel: 255,
    maxChannel: 0,
    painted: false,
  };
}

/**
 * Downsample one same-origin PDF.js canvas and verify that it contains visible
 * pixels. This is intentionally content-agnostic: no text extraction or OCR.
 */
export function inspectCanvasPaint(canvas: HTMLCanvasElement): CanvasPaintInspection {
  const inspection = emptyInspection(canvas);
  if (canvas.width < 1 || canvas.height < 1) return inspection;

  const scale = Math.min(1, MAX_AUDIT_EDGE / canvas.width, MAX_AUDIT_EDGE / canvas.height);
  const width = Math.max(1, Math.round(canvas.width * scale));
  const height = Math.max(1, Math.round(canvas.height * scale));
  const auditCanvas = document.createElement("canvas");
  auditCanvas.width = width;
  auditCanvas.height = height;
  const context = auditCanvas.getContext("2d", {
    alpha: false,
    willReadFrequently: true,
  });
  if (context === null) return inspection;

  try {
    context.drawImage(canvas, 0, 0, width, height);
    const pixels = context.getImageData(0, 0, width, height).data;
    let nonWhitePixels = 0;
    let minChannel = 255;
    let maxChannel = 0;
    for (let offset = 0; offset < pixels.length; offset += 4) {
      const red = pixels[offset];
      const green = pixels[offset + 1];
      const blue = pixels[offset + 2];
      const alpha = pixels[offset + 3];
      minChannel = Math.min(minChannel, red, green, blue);
      maxChannel = Math.max(maxChannel, red, green, blue);
      if (
        alpha > 0 &&
        (red < WHITE_CHANNEL_THRESHOLD ||
          green < WHITE_CHANNEL_THRESHOLD ||
          blue < WHITE_CHANNEL_THRESHOLD)
      ) {
        nonWhitePixels += 1;
      }
    }
    return {
      width: canvas.width,
      height: canvas.height,
      sampledPixels: width * height,
      nonWhitePixels,
      minChannel,
      maxChannel,
      painted: nonWhitePixels > 0,
    };
  } catch {
    return inspection;
  } finally {
    auditCanvas.width = 0;
    auditCanvas.height = 0;
  }
}
