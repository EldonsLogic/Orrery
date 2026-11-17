// Static export: the app renders in the browser; no server code touches tenant data (ADR-0022).
/** @type {import('next').NextConfig} */
export default {
  output: 'export',
  trailingSlash: true,
  reactStrictMode: true,
};
