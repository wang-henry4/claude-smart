export const dynamic = "force-static";

export function GET() {
  return new Response(JSON.stringify({ service: "claude-smart-dashboard" }), {
    headers: {
      "content-type": "application/json",
      "x-claude-smart-dashboard": "1",
    },
  });
}
