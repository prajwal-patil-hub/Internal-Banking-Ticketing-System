// The `lint` script has been in package.json since P0 but there was never a
// config for it to read, so it failed on startup and was never wired into CI.
// The plugins it names were installed all along.
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['@typescript-eslint', 'react-refresh'],
  ignorePatterns: ['dist', 'node_modules', '*.cjs', 'vite.config.ts', 'vitest.config.ts'],
  rules: {
    // The single most valuable rule here: a missing dependency is a stale
    // closure, which shows up as a component that silently stops updating
    // rather than as an error anyone can see.
    'react-hooks/exhaustive-deps': 'warn',

    // `_unused` is the conventional way to say "deliberately ignored" — for a
    // destructured value or an unused callback argument.
    '@typescript-eslint/no-unused-vars': [
      'error',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
    ],

    // Tolerated rather than endorsed: `any` appears where third-party types
    // are wrong or absent. Warned so it stays visible without blocking.
    '@typescript-eslint/no-explicit-any': 'warn',

    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
  },
  overrides: [
    {
      // Vitest globals are configured in vitest.config.ts, not imported.
      files: ['**/*.test.ts', '**/*.test.tsx', 'src/test/**'],
      env: { node: true },
      globals: { describe: 'readonly', it: 'readonly', expect: 'readonly', vi: 'readonly' },
    },
  ],
};
