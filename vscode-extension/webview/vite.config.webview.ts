import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// Standalone Svelte build for VS Code webview (no SvelteKit routing)
export default defineConfig({
  plugins: [
    tailwindcss(),
    svelte(),
    {
      name: "add-dark-class",
      transformIndexHtml(html) {
        return html.replace("<body>", '<body class="dark">');
      },
    },
  ],
  build: {
    outDir: "build",
    emptyOutDir: true,
    // Inline all dependencies to avoid module resolution issues in webview
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "index.html"),
      },
      output: {
        entryFileNames: "assets/[name].[hash].js",
        chunkFileNames: "assets/[name].[hash].js",
        assetFileNames: "assets/[name].[hash].[ext]",
        // Keep ES modules format but inline everything
        format: "es",
        // Inline all dependencies into a single bundle
        inlineDynamicImports: true,
      },
    },
    // Don't minify for easier debugging
    minify: false,
    // Inline small assets
    assetsInlineLimit: 4096,
    // Target modern browsers (webview uses recent Chromium)
    target: "esnext",
  },
  resolve: {
    alias: {
      $lib: path.resolve(__dirname, "src/lib"),
      "@shared": path.resolve(__dirname, "../../shared"),
      "@extension-config": path.resolve(__dirname, "../src/config"),
      "@extension-shared": path.resolve(__dirname, "../src/shared"),
    },
  },
});
