import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// Port 8090 keeps the portal clearly separate from the public site on 8080.
export default defineConfig({
  server: { host: "127.0.0.1", port: 8090 },
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
});
