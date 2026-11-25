/** Presentation preferences only; document drafts keep their existing stores and contracts. */
import { createContext, useContext } from "react";
export const interfacePreferenceKey = "mathmongo-interface-v1";
export type InterfacePreferences = {
  theme: "dark" | "light";
  libraryView: "cards" | "list";
  density: "comfortable" | "compact";
  navigationCollapsed: boolean;
  contextOpen: boolean;
  contextWidth: number;
};
export const defaultInterface: InterfacePreferences = {
  theme: "dark",
  libraryView: "cards",
  density: "comfortable",
  navigationCollapsed: false,
  contextOpen: true,
  contextWidth: 300,
};
export function readInterfacePreferences(): InterfacePreferences {
  try {
    const value = JSON.parse(
      localStorage.getItem(interfacePreferenceKey) || "{}",
    );
    if (!value || typeof value !== "object" || Array.isArray(value))
      return { ...defaultInterface };
    return {
      theme: value.theme === "light" ? "light" : "dark",
      libraryView: value.libraryView === "list" ? "list" : "cards",
      density: value.density === "compact" ? "compact" : "comfortable",
      navigationCollapsed: value.navigationCollapsed === true,
      contextOpen: value.contextOpen !== false,
      contextWidth:
        typeof value.contextWidth === "number" &&
        Number.isFinite(value.contextWidth)
          ? Math.max(240, Math.min(440, value.contextWidth))
          : 300,
    };
  } catch {
    return { ...defaultInterface };
  }
}
export const InterfaceContext = createContext({
  preferences: defaultInterface,
  change: (_patch: Partial<InterfacePreferences>) => {},
  problem: "",
});
export const useInterfacePreferences = () => useContext(InterfaceContext);
