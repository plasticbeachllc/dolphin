import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  optimizeDeps: {
    // Exclude gallery pages from dependency scanning to avoid false positives
    // from code examples that reference React/axios/etc in mock data
    exclude: ["react", "react-router-dom", "axios"],
    entries: [
      "src/routes/+layout.svelte",
      "src/routes/+page.svelte",
      "src/routes/code/+page.svelte",
      "src/routes/kb/+page.svelte",
      "src/routes/profile/+page.svelte",
      "src/routes/settings/+page.svelte",
      "src/routes/test-tools/+page.svelte",
      "src/routes/functions/code-review/+page.svelte",
      "src/routes/functions/architect/+page.svelte",
      "src/routes/tools/analyze/+page.svelte",
      "src/routes/tools/docs/+page.svelte",
      "src/routes/tools/refactor/+page.svelte",
      "src/routes/tools/tests/+page.svelte",
      // Exclude gallery pages - they contain code examples
      // that reference React/axios but are just mock data strings
      "!src/routes/gallery/**/*.svelte",
    ],
  },
});
