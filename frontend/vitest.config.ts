import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Separate from vite.config.ts on purpose: the build config carries
// `manualChunks`, which is meaningless under test and produces a warning on
// every run. The two share only what they need to — the React plugin and the
// `@` alias, so imports resolve identically in tests and in the app.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
});
