import type { NextConfig } from "next";

/**
 * Two build modes, one codebase.
 *
 * Normal (`npm run dev`, `npm run build`): a server build including the three
 * API route handlers that proxy to the gateway. This is the real product.
 *
 * `NEXT_PUBLIC_STATIC_DEMO=1`: a fully static export for GitHub Pages, which
 * serves files and cannot run route handlers or reach Postgres. The CI workflow
 * deletes `app/api/` before building for exactly this reason — a POST handler
 * has no static equivalent, so leaving them in place fails the export outright.
 */
const isStaticDemo = process.env.NEXT_PUBLIC_STATIC_DEMO === "1";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = isStaticDemo
  ? {
      output: "export",
      basePath: basePath || undefined,
      // Pages has no image optimiser behind it.
      images: { unoptimized: true },
      // Pages serves /route as /route/index.html.
      trailingSlash: true,
    }
  : {};

export default nextConfig;
