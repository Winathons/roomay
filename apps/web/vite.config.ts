import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// "@tabler/icons-react" resolves to src/icons.js, a small generated module that re-exports only
// the icons Roomay uses (regenerate with `npm run icons`). Types still come from the real package.
// Without this, Vite pre-bundles all 5,000+ icons and dev start-up stalls.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@tabler/icons-react": "/src/icons.js" } },
  optimizeDeps: { include: ["react", "react-dom", "react-dom/client", "react/jsx-dev-runtime"], exclude: ["@tabler/icons-react"] },
});
