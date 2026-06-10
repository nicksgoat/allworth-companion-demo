// Allworth Client Intelligence MCP server (stdio).
//
// Per docs/MCP_INTEGRATION.md connector rules: MCP is a backend capability
// layer — read-only first, entitlement-scoped to one household (clientId is
// pinned server-side, never a tool parameter), and every result carries a
// source label and timestamp so downstream consumers treat it as a source
// episode, not final client truth.
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { toolDefinitions, runTool } from "../lib/tools.js";

const CLIENT_ID = process.env.ALLWORTH_CLIENT_ID || "maya";
const SOURCE = "allworth-demo-backend";

// Read-only first: writes (update_client_profile) need approval + audit design.
const READ_ONLY_TOOLS = toolDefinitions.filter((t) => t.name !== "update_client_profile");

const server = new Server(
  { name: "allworth-client-intelligence", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: READ_ONLY_TOOLS.map((t) => ({
    name: t.name,
    description: t.description,
    inputSchema: t.input_schema,
  })),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  if (!READ_ONLY_TOOLS.some((t) => t.name === name)) {
    return {
      content: [{ type: "text", text: `Tool not available over MCP (read-only boundary): ${name}` }],
      isError: true,
    };
  }
  const data = runTool(name, args ?? {}, CLIENT_ID);
  const envelope = {
    source: SOURCE,
    tool: name,
    clientId: CLIENT_ID,
    retrieved_at: new Date().toISOString(),
    read_only: true,
    data,
  };
  return {
    content: [{ type: "text", text: JSON.stringify(envelope, null, 2) }],
    isError: Boolean(data?.error),
  };
});

await server.connect(new StdioServerTransport());
console.error(`[mcp] allworth-client-intelligence ready (client: ${CLIENT_ID}, ${READ_ONLY_TOOLS.length} read-only tools)`);
