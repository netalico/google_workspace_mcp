import { Container, getContainer } from "@cloudflare/containers";

interface Env {
	WORKSPACE_MCP: DurableObjectNamespace<WorkspaceMcp>;
	GOOGLE_OAUTH_CLIENT_ID: string;
	GOOGLE_OAUTH_CLIENT_SECRET: string;
	GCP_SA_KEY_JSON: string;
}

export class WorkspaceMcp extends Container<Env> {
	defaultPort = 8000;
	// OAuth 2.1 sessions live in-process; keep the instance warm through a workday lull.
	sleepAfter = "2h";

	constructor(ctx: DurableObjectState, env: Env) {
		super(ctx, env);
		this.envVars = {
			MCP_ENABLE_OAUTH21: "true",
			WORKSPACE_EXTERNAL_URL: "https://workspace-mcp.netalico.com",
			PORT: "8000",
			TOOL_TIER: "core",
			WORKSPACE_MCP_CREDENTIAL_STORE_BACKEND: "gcs",
			WORKSPACE_MCP_GCS_BUCKET: "netalico-workspace-mcp-creds",
			WORKSPACE_MCP_BRAND_NAME: "Netalico Workspace MCP",
			GOOGLE_OAUTH_CLIENT_ID: env.GOOGLE_OAUTH_CLIENT_ID,
			GOOGLE_OAUTH_CLIENT_SECRET: env.GOOGLE_OAUTH_CLIENT_SECRET,
			GCP_SA_KEY_JSON: env.GCP_SA_KEY_JSON,
		};
	}
}

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		// Single shared instance: OAuth 2.1 session state is in-memory in the
		// container, so every request must land on the same one.
		return getContainer(env.WORKSPACE_MCP, "main").fetch(request);
	},

	async scheduled(_controller: ScheduledController, env: Env): Promise<void> {
		// Keep-warm: a cold boot (Python on 0.25 vCPU) takes longer than
		// claude.ai's connector timeout, so never let the container sleep.
		// Idle CPU is usage-billed; always-on costs ~$7/mo in memory+disk.
		await getContainer(env.WORKSPACE_MCP, "main").fetch(
			new Request("http://container/health"),
		);
	},
};
