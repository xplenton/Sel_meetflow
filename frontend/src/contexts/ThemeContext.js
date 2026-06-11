import { createContext, useContext, useEffect, useState, useCallback } from 'react';

/**
 * Dark-mode toggle for clinic night shifts (iter 124).
 *
 * Strategy: a root-level `html.dark` class pairs with a targeted CSS layer
 * in `index.css` that re-maps the app's hardcoded hex palette for dark
 * contexts. `system` follows the OS `prefers-color-scheme` media query.
 *
 * Persistence: localStorage only. Intentionally NOT persisted server-side
 * yet — each device can have its own preference (a nurse's shared
 * workstation likely wants light during day even if they prefer dark on
 * their phone).
 */
const ThemeContext = createContext(null);

const STORAGE_KEY = 'mf_theme'; // 'light' | 'dark' | 'system'

function applyThemeClass(mode) {
  const root = document.documentElement;
  const systemDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
  const shouldBeDark = mode === 'dark' || (mode === 'system' && systemDark);
  root.classList.toggle('dark', shouldBeDark);
  root.dataset.theme = shouldBeDark ? 'dark' : 'light';
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) || 'light'; }
    catch { return 'light'; }
  });

  const setTheme = useCallback((next) => {
    setThemeState(next);
    try { localStorage.setItem(STORAGE_KEY, next); } catch { /* ignore */ }
    applyThemeClass(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  }, [theme, setTheme]);

  // Apply on mount + whenever system preference flips (if mode=system)
  useEffect(() => {
    applyThemeClass(theme);
    if (theme !== 'system') return;
    const mql = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!mql) return;
    const onChange = () => applyThemeClass('system');
    mql.addEventListener?.('change', onChange);
    return () => mql.removeEventListener?.('change', onChange);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext) || { theme: 'light', setTheme: () => {}, toggleTheme: () => {} };
}
