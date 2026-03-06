import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = "http://127.0.0.1:8000/generate_character";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const res = await fetch(BACKEND_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (err) {
    console.error("Error proxying generate_character:", err);
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
