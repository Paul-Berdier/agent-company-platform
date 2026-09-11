import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  server: { port: 5173 },
  build: {
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, "index.html"),
        // mode wallpaper autonome (second écran, Wallpaper Engine futur)
        ambient: resolve(import.meta.dirname, "ambient.html"),
      },
    },
  },
});
