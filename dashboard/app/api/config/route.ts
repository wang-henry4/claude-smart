import { NextResponse } from "next/server";
import { readConfig, writeConfig } from "@/lib/config-file";

export const dynamic = "force-dynamic";

export async function GET() {
  const config = await readConfig();
  return NextResponse.json(config);
}

export async function PUT(req: Request) {
  const body = await req.json();
  await writeConfig(body);
  const config = await readConfig();
  return NextResponse.json(config);
}
