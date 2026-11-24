/** Small forms retain values and the exact pending request, scoped to the library. */
import { useRef, useState } from "react";

export function useLocalForm<T extends object>(key: string, initial: () => T) {
  const corrupt = useRef(false);
  const [state, update] = useState<T>(() => {
    const fallback = initial();
    try {
      const value = localStorage.getItem(key);
      if (!value) return fallback;
      const parsed = JSON.parse(value);
      if (
        !parsed ||
        typeof parsed !== "object" ||
        Array.isArray(parsed) ||
        Object.keys(fallback).some(
          (field) => typeof parsed[field] !== typeof fallback[field as keyof T],
        )
      )
        throw new Error("invalid draft");
      return parsed as T;
    } catch {
      corrupt.current = true;
      return fallback;
    }
  });
  const [problem, setProblem] = useState(
    corrupt.current
      ? "El borrador anterior no se pudo leer y se conserva intacto. Descárgalo antes de iniciar otra ficha."
      : "",
  );
  const set = (next: T) => {
    update(next);
    if (corrupt.current) return false;
    try {
      localStorage.setItem(key, JSON.stringify(next));
      setProblem("");
      return true;
    } catch {
      setProblem(
        "El navegador no pudo conservar el borrador. Mantén esta página abierta y descarga tu trabajo antes de salir.",
      );
      return false;
    }
  };
  const download = () => {
    const content = corrupt.current
      ? (localStorage.getItem(key) ?? "")
      : JSON.stringify(state, null, 2);
    const url = URL.createObjectURL(
      new Blob([content], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "mathmongo-borrador.json";
    link.click();
    URL.revokeObjectURL(url);
  };
  const restart = () => {
    try {
      const original = localStorage.getItem(key);
      if (original !== null)
        localStorage.setItem(key + "-archive-" + crypto.randomUUID(), original);
      const next = initial();
      localStorage.setItem(key, JSON.stringify(next));
      corrupt.current = false;
      update(next);
      setProblem("");
      return true;
    } catch {
      setProblem(
        "No se pudo conservar una copia. El borrador original sigue intacto; descárgalo y recupera el almacenamiento.",
      );
      return false;
    }
  };
  return {
    state,
    set,
    problem,
    download,
    restart,
    clear: () => {
      if (!corrupt.current)
        try {
          localStorage.removeItem(key);
        } catch {
          setProblem(
            "La ficha se guardó, pero no se pudo retirar su borrador local.",
          );
        }
    },
  };
}
