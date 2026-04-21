import { NextResponse } from "next/server";
import { originOnly } from "@/lib/reflexio-url";

export const dynamic = "force-dynamic";

const DEFAULT_URL = "http://localhost:8081";

function reflexioBase(req: Request): string {
  const header = req.headers.get("x-reflexio-url");
  const fromHeader = header ? originOnly(header) : null;
  if (fromHeader) return fromHeader;
  const fromEnv = originOnly(process.env.REFLEXIO_URL ?? "");
  return fromEnv ?? DEFAULT_URL;
}

async function proxy(
  req: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const targetPath = path.join("/");
  const url = new URL(req.url);
  const target = `${reflexioBase(req)}/${targetPath}${url.search}`;

  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("x-reflexio-url");
  headers.delete("connection");

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  try {
    const upstream = await fetch(target, init);
    const buf = await upstream.arrayBuffer();
    return new NextResponse(buf, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/octet-stream",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: "reflexio unreachable", detail: message, target },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
