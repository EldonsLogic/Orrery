// Marketing: fully static, no customer data (ADR-0022).
/** @type {import('next').NextConfig} */
export default {
  output: 'export',
  trailingSlash: true,
  reactStrictMode: true,
  agentRules: false, // do not generate an AGENTS.md; the repo root AGENTS.md is the only one
};
