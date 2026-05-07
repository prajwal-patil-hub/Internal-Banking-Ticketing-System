import { create } from 'zustand';

type Theme = 'light' | 'dark';

interface ThemeState {
  theme: Theme;
  toggle: () => void;
  set: (t: Theme) => void;
}

// Default to light unless the user has explicitly chosen dark before.
// We intentionally do NOT honour `prefers-color-scheme: dark` on first visit —
// this is an enterprise app for branch staff who often work under bright
// fluorescent lighting and were surprised to land in a dark UI.
const initial: Theme =
  (localStorage.getItem('theme') as Theme | null) ?? 'light';

document.documentElement.classList.toggle('dark', initial === 'dark');

export const useTheme = create<ThemeState>((set, get) => ({
  theme: initial,
  set: (t) => {
    localStorage.setItem('theme', t);
    document.documentElement.classList.toggle('dark', t === 'dark');
    set({ theme: t });
  },
  toggle: () => {
    const next: Theme = get().theme === 'dark' ? 'light' : 'dark';
    get().set(next);
  },
}));
