import { NextResponse } from "next/server";
import { listSessions } from "@/lib/session-reader";

export const dynamic = "force-dynamic";

export async function GET() {
  const sessions = await listSessions();
  return NextResponse.json({ sessions });
}
