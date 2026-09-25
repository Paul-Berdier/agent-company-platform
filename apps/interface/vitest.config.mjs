// Tests unitaires des greffons (Vitest, happy-dom). JSX « classique » comme le bundle (fabrique h
// de src/react.ts, qui prend React sur le SDK : ici le SDK factice de tests/sdk-factice.ts).
import { defineConfig } from "vitest/config";

export default defineConfig({
  oxc: { jsx: { runtime: "classic", pragma: "h", pragmaFrag: "Fragment" } },
  test: {
    environment: "happy-dom",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    setupFiles: ["tests/preparation.ts"],
    restoreMocks: true,
  },
});
