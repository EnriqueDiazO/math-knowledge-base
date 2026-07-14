import { afterEach, describe, expect, it, vi } from "vitest";

import { inspectCanvasPaint } from "../src/pdf/canvasPaint";

interface AuditContextFixture {
  drawImage: ReturnType<typeof vi.fn>;
  getImageData: ReturnType<typeof vi.fn>;
}

function rgbaPixels(width: number, height: number): Uint8ClampedArray {
  const pixels = new Uint8ClampedArray(width * height * 4);
  pixels.fill(255);
  return pixels;
}

function installAuditContext(
  pixelsFor: (width: number, height: number) => Uint8ClampedArray,
): AuditContextFixture {
  const fixture: AuditContextFixture = {
    drawImage: vi.fn(),
    getImageData: vi.fn((_x: number, _y: number, width: number, height: number) => ({
      data: pixelsFor(width, height),
    })),
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    fixture as unknown as CanvasRenderingContext2D,
  );
  return fixture;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("inspectCanvasPaint", () => {
  it("bounds the audit dimensions and identifies a completely white canvas", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 480;
    const context = installAuditContext(rgbaPixels);

    const inspection = inspectCanvasPaint(canvas);

    expect(context.drawImage).toHaveBeenCalledWith(canvas, 0, 0, 160, 120);
    expect(context.getImageData).toHaveBeenCalledWith(0, 0, 160, 120);
    expect(inspection).toEqual({
      width: 640,
      height: 480,
      sampledPixels: 19_200,
      nonWhitePixels: 0,
      minChannel: 255,
      maxChannel: 255,
      painted: false,
    });
  });

  it("detects a visible non-white pixel after downsampling", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 1_000;
    canvas.height = 2_000;
    installAuditContext((width, height) => {
      const pixels = rgbaPixels(width, height);
      pixels[0] = 12;
      pixels[1] = 96;
      pixels[2] = 180;
      return pixels;
    });

    const inspection = inspectCanvasPaint(canvas);

    expect(inspection).toEqual({
      width: 1_000,
      height: 2_000,
      sampledPixels: 12_800,
      nonWhitePixels: 1,
      minChannel: 12,
      maxChannel: 255,
      painted: true,
    });
  });

  it("does not inspect a zero-sized canvas", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 0;
    canvas.height = 240;
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext");

    expect(inspectCanvasPaint(canvas)).toEqual({
      width: 0,
      height: 240,
      sampledPixels: 0,
      nonWhitePixels: 0,
      minChannel: 255,
      maxChannel: 0,
      painted: false,
    });
    expect(getContext).not.toHaveBeenCalled();
  });
});
