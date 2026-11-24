/** Raster previews use the existing img-src data: policy, without enabling blob: images. */
export function pngDataUri(blob: Blob): Promise<string> {
  if (blob.type !== "image/png" || blob.size > 16 * 1024 * 1024)
    throw new Error(
      "La vista previa no contiene una imagen PNG válida. Reintenta su generación.",
    );
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () =>
      reject(
        new Error(
          "No pudimos leer la imagen de vista previa. El código se conserva.",
        ),
      );
    reader.onload = () =>
      typeof reader.result === "string"
        ? resolve(reader.result)
        : reject(new Error("No se confirmó la imagen de vista previa."));
    reader.readAsDataURL(blob);
  });
}
