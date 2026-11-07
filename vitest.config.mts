import { defineConfig } from "vitest/config";

export default defineConfig({
    test: {
        environment: "jsdom",
        include: ["n26/frontend/**/*.test.{ts,tsx,js}"],
        setupFiles: ["n26/frontend/test/setup.ts"],
    },
});
