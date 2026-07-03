import { Container, getContainer } from "@cloudflare/containers";
import { env } from "cloudflare:workers";

export class ApronContainer extends Container {
  defaultPort = 8000;
  sleepAfter = "10m";
  // Paperless141 credentials go into the container; APRONMCP_TOKEN stays in the Worker.
  envVars = {
    PAPERLESS_USER: (env as Record<string, string>).PAPERLESS_USER ?? "",
    PAPERLESS_PASS: (env as Record<string, string>).PAPERLESS_PASS ?? "",
    PAPERLESS_BASE_URL:
      (env as Record<string, string>).PAPERLESS_BASE_URL ??
      "https://advantage.paperlessfbo.com",
  };
}

interface WorkerEnv {
  APRONMCP_TOKEN: string;
  APRON_CONTAINER: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, workerEnv: WorkerEnv): Promise<Response> {
    const auth = request.headers.get("Authorization") ?? "";
    if (!workerEnv.APRONMCP_TOKEN || auth !== `Bearer ${workerEnv.APRONMCP_TOKEN}`) {
      return new Response("Unauthorized", { status: 401 });
    }
    const { pathname } = new URL(request.url);
    if (pathname === "/mcp" || pathname.startsWith("/mcp/")) {
      // Fixed instance name -> exactly one container / one Paperless141 login.
      return getContainer(workerEnv.APRON_CONTAINER, "singleton").fetch(request);
    }
    return new Response("Not found", { status: 404 });
  },
};
