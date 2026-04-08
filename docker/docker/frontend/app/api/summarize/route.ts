import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  const backendBaseUrl = process.env.BACKEND_BASE_URL;
  const devJwtToken = process.env.DEV_JWT_TOKEN;

  if (!backendBaseUrl || !devJwtToken) {
    return new Response(
      JSON.stringify({ error: "Server configuration error" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }

  const body = await request.json();
  const text = typeof body.prompt === "string" ? body.prompt.trim() : "";

  if (!text) {
    return new Response(
      JSON.stringify({ error: "Prompt is required" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  const res = await fetch(`${backendBaseUrl}/summarize`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${devJwtToken}`,
    },
    body: JSON.stringify({ text, max_length: 100 }),
  });

  if (!res.ok) {
    const errText = await res.text();
    return new Response(
      JSON.stringify({ error: errText || `Backend error: ${res.status}` }),
      { status: res.status, headers: { "Content-Type": "application/json" } }
    );
  }

  const data = (await res.json()) as { summary: string };
  return new Response(data.summary, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
