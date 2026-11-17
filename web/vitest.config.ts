import { defineConfig } from 'vitest/config';

export default defineConfig({
  // Vite 8 transforms with oxc; the apps' tsconfig has jsx "preserve" for Next, so set the runtime here.
  oxc: { jsx: { runtime: 'automatic' } },
  test: { include: ['app/src/**/*.test.{ts,tsx}'] },
});
