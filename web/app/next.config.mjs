// Static export: the app renders in the browser; no server code touches tenant data (ADR-0022).
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** @type {import('next').NextConfig} */
export default {
  // The login checks tenant colours against the platform surface in docs/brand/tokens (read-only import), so the bundler root is the repo root.
  turbopack: { root: resolve(dirname(fileURLToPath(import.meta.url)), '../..') },
  output: 'export',
  trailingSlash: true,
  reactStrictMode: true,
  agentRules: false, // do not generate an AGENTS.md; the repo root AGENTS.md is the only one
};
