import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirror the "@/*" import alias from tsconfig.json.
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    // `app/**` was excluded, so the four routes and the three API proxies -
    // which hold every 400/502/503 branch the UI depends on - had no tests, and
    // a test placed there would silently not run. Route-handler tests opt into
    // the node environment with a `@vitest-environment node` docblock.
    include: [
      "lib/**/*.test.ts",
      "lib/**/*.test.tsx",
      "components/**/*.test.tsx",
      "app/**/*.test.ts",
      "app/**/*.test.tsx",
    ],
    coverage: {
      include: ["app/**", "components/**", "lib/**"],
      // layout.tsx is Next.js plumbing with no branches; catalogStats.ts is
      // generated constants (its agreement with the catalog is checked by
      // lib/catalogStats.test.ts, which coverage cannot express).
      exclude: ["**/*.test.*", "app/layout.tsx", "lib/catalogStats.ts"],
      // Floors set just under what the suite achieves today, so this ratchets
      // rather than blocks. Deliberately lower than the gateway's 70% across
      // the board: most of what is uncovered here is presentational JSX.
      thresholds: { statements: 78, lines: 80, functions: 64, branches: 66 },
    },
  },
});
