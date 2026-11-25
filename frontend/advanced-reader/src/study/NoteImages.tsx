/** On-demand previews of the same saved resources used by the canonical PDF exporter. */
import { useEffect, useState } from "react";
import { studyBinary, type StudyContext } from "./api";
import { useStudyResource } from "./navigation";
import "./note-images.css";
type ImageRecord = {
  asset_id: string;
  name: string;
  state: "ready" | "missing";
  watermark: boolean;
};
function Preview({
  context,
  path,
  image,
}: {
  context: StudyContext;
  path: string;
  image: ImageRecord;
}) {
  const [url, setUrl] = useState(""),
    [error, setError] = useState(""),
    [pdf, setPdf] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let owned = "";
    studyBinary(
      path + "/" + encodeURIComponent(image.asset_id),
      context,
      undefined,
      controller.signal,
    )
      .then((blob) => {
        if (controller.signal.aborted) return;
        owned = URL.createObjectURL(blob);
        setUrl(owned);
        setPdf(blob.type === "application/pdf");
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason.message);
      });
    return () => {
      controller.abort();
      if (owned) URL.revokeObjectURL(owned);
    };
  }, [context, path, image.asset_id]);
  return (
    <figure>
      {error ? (
        <p role="alert">{error}</p>
      ) : url ? (
        pdf ? (
          <a href={url} download={image.name}>
            Descargar imagen PDF
          </a>
        ) : (
          <img src={url} alt={image.name} />
        )
      ) : (
        <p role="status">Cargando imagen…</p>
      )}
      <figcaption>
        {image.name}
        {image.watermark && " · Marca de agua"}
      </figcaption>
    </figure>
  );
}
function Gallery({ context, path }: { context: StudyContext; path: string }) {
  const resource = useStudyResource<{ images: ImageRecord[] }>(context, path);
  return (
    <div>
      {resource.error && (
        <p role="alert">
          {resource.error}{" "}
          <button onClick={resource.retry}>Reintentar imágenes</button>
        </p>
      )}
      {resource.data?.images.length === 0 && (
        <p>Esta nota no tiene imágenes asociadas.</p>
      )}
      <div className="study-note-images">
        {resource.data?.images.map((image) =>
          image.state === "missing" ? (
            <p role="alert" key={image.asset_id}>
              {image.name}: falta el archivo. Vuelve a asociarlo en las imágenes
              de la nota antes de exportar.
            </p>
          ) : (
            <Preview
              key={context.library_id + image.asset_id}
              context={context}
              path={path}
              image={image}
            />
          ),
        )}
      </div>
    </div>
  );
}
export function NoteImages({
  context,
  family,
  identity,
}: {
  context: StudyContext;
  family: string;
  identity: string;
}) {
  const [open, setOpen] = useState(false),
    path =
      "/structured/" + family + "/" + encodeURIComponent(identity) + "/images";
  return (
    <details
      className="study-resource-panel"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Imágenes de esta nota</summary>
      <p>
        Recursos de la versión guardada, incluidos en el proyecto y el PDF.
        Abrirlos no modifica la nota.
      </p>
      {open &&
        (context.capabilities?.includes("structured-images") ? (
          <Gallery context={context} path={path} />
        ) : (
          <p>
            La instancia abierta necesita cargar los servicios actuales para
            mostrar las imágenes. Conserva el borrador y vuelve a iniciar
            MathMongo; los archivos originales se mantienen.
          </p>
        ))}
    </details>
  );
}
