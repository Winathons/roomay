import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@tabler/icons-react": "/src/icons.js" } },
  optimizeDeps: { include: ["react", "react-dom", "react-dom/client", "react/jsx-dev-runtime"], exclude: ["@tabler/icons-react"] },
});
