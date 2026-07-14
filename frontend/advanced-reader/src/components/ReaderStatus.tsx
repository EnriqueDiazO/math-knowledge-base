interface ReaderStatusProps {
  kind: "loading" | "error";
  title: string;
  message: string;
  onRetry?: () => void;
}

export function ReaderStatus({ kind, title, message, onRetry }: ReaderStatusProps) {
  return (
    <main className={`reader-status ${kind}`} role={kind === "error" ? "alert" : "status"}>
      <div className="reader-mark" aria-hidden="true">∫</div>
      <p className="eyebrow">MathMongo Advanced Reader</p>
      <h1>{title}</h1>
      <p>{message}</p>
      {onRetry && <button type="button" onClick={onRetry}>Reintentar</button>}
    </main>
  );
}
