import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

function desktopDevelopment(): Plugin {
  return {
    name: "classfox-development-connection",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/__classfox", (request, response) => {
        const origin = request.headers.origin;
        const host = request.headers.host;
        const allowedHosts = ["localhost:1420", "127.0.0.1:1420"];
        if (
          !host ||
          !allowedHosts.includes(host) ||
          (origin && origin !== `http://${host}`) ||
          request.headers["sec-fetch-site"] === "cross-site"
        ) {
          response.writeHead(403);
          response.end();
          return;
        }
        const token = process.env.CLASSFOX_DEV_TOKEN;
        const port = Number(process.env.CLASSFOX_PORT);
        if (!token || !Number.isInteger(port) || port < 1 || port > 65535) {
          response.writeHead(503, { "Content-Type": "application/json" });
          response.end(
            JSON.stringify({ message: "Start the development backend first" }),
          );
          return;
        }
        response.writeHead(200, {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        });
        response.end(
          JSON.stringify({ baseUrl: `http://127.0.0.1:${port}`, token }),
        );
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), desktopDevelopment()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: "127.0.0.1",
    watch: { ignored: ["**/src-tauri/**"] },
  },
});
