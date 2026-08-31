import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

function required(name: string): string {
    const value = process.env[name];
    if (!value) {
        throw new Error(`${name} is required`);
    }
    return value;
}

export default async function (pi: ExtensionAPI) {
    const command = required("ADS_MCP_COMMAND");
    const transport = new StdioClientTransport({
        command,
        env: { ...process.env } as Record<string, string>,
        stderr: "pipe",
    });
    const client = new Client({ name: "pi-ads-benchmark-adapter", version: "1.0.0" });
    await client.connect(transport);

    const listed = await client.listTools();
    for (const tool of listed.tools) {
        pi.registerTool({
            name: tool.name,
            label: `ADS MCP: ${tool.name}`,
            description: tool.description ?? `Official ADS MCP tool ${tool.name}`,
            parameters: tool.inputSchema as any,
            execute: async (_toolCallId, params) => {
                const result = await client.callTool({ name: tool.name, arguments: params });
                const text = result.content
                    .map((block) => block.type === "text" ? block.text : JSON.stringify(block))
                    .join("\n");
                return {
                    content: [{ type: "text" as const, text }],
                    details: { isError: Boolean(result.isError) },
                    isError: Boolean(result.isError),
                };
            },
        });
    }

    pi.on("session_shutdown", async () => {
        await client.close();
    });
}
