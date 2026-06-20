import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    "process.env": {},
    global: "globalThis",
  },
  optimizeDeps: {
    include: ["ketcher-react", "ketcher-core", "lodash", "@babel/runtime/regenerator"],
    exclude: ["ketcher-standalone/dist/binaryWasm"],
    esbuildOptions: {
      define: {
        "process.env": "{}",
        global: "globalThis",
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
