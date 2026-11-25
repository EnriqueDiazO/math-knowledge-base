import { useState, type ReactNode } from "react";
import {
  InterfaceContext,
  interfacePreferenceKey,
  readInterfacePreferences,
  type InterfacePreferences,
} from "./interface-preferences";
export function InterfacePreferencesProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [preferences, setPreferences] = useState(readInterfacePreferences),
    [problem, setProblem] = useState("");
  function change(patch: Partial<InterfacePreferences>) {
    const next = { ...preferences, ...patch };
    setPreferences(next);
    try {
      localStorage.setItem(interfacePreferenceKey, JSON.stringify(next));
      setProblem("");
    } catch {
      setProblem(
        "La preferencia se aplica en esta ventana, pero el navegador no pudo conservarla para la próxima sesión.",
      );
    }
  }
  return (
    <InterfaceContext.Provider value={{ preferences, change, problem }}>
      {children}
    </InterfaceContext.Provider>
  );
}
