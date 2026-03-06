import { NextResponse } from "next/server";

const BACKEND_URL = "http://127.0.0.1:8000/health";

export async function GET() {
  try {
    const res = await fetch(BACKEND_URL, { cache: "no-store" });
    const text = await res.text();
    return new NextResponse(text, { status: res.status });
  } catch (err) {
    console.error("Error proxying health:", err);
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
