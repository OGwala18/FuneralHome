import { useSyncExternalStore } from "react";

/**
 * Light/dark theme.
 *
 * Until someone presses the toggle we follow the operating system, and keep
 * following it if they change it. The moment they choose explicitly, that
 * choice sticks and the system preference stops overriding it.
 *
 * A tiny external store rather than context: the toggle lives in the header but
 * any component can read the theme, and nothing needs a provider. Unlike the
 * language switcher this never reloads the page — a theme change should be
 * instant.
 */

export type Theme = "light" | "dark";

const STORAGE_KEY = "induduzo-theme";

const listeners = new Set<() => void>();

const systemPrefersDark = (): boolean => {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return false;
  }
};

const readStoredChoice = (): Theme | null => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    // Private browsing can refuse storage. We just fall back to the system.
    return null;
  }
};

let hasExplicitChoice = readStoredChoice() !== null;
let current: Theme = readStoredChoice() ?? (systemPrefersDark() ? "dark" : "light");

const applyToDocument = (theme: Theme) => {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  // Tells the browser to render native widgets (scrollbars, date pickers,
  // form controls) in the matching scheme.
  root.style.colorScheme = theme;
};

// The inline script in index.html has already set the class to avoid a flash of
// the wrong theme; this keeps the module's view of the world in sync with it.
if (typeof document !== "undefined") {
  applyToDocument(current);

  try {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (event) => {
      if (hasExplicitChoice) return;
      current = event.matches ? "dark" : "light";
      applyToDocument(current);
      listeners.forEach((listener) => listener());
    });
  } catch {
    /* older browsers: no live system-change following, which is fine */
  }
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

const getSnapshot = (): Theme => current;

export const setTheme = (theme: Theme) => {
  current = theme;
  hasExplicitChoice = true;
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* no-op */
  }
  applyToDocument(theme);
  listeners.forEach((listener) => listener());
};

export const toggleTheme = () => setTheme(current === "dark" ? "light" : "dark");

export const useTheme = () => {
  // Server snapshot is "light": the inline script corrects it before paint.
  const theme = useSyncExternalStore(subscribe, getSnapshot, () => "light" as Theme);
  return { theme, setTheme, toggleTheme };
};
