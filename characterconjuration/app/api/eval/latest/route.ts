import { NextResponse } from "next/server";

const BACKEND_URL = "http://127.0.0.1:8000/eval/latest";

export async function GET() {
  try {
    const res = await fetch(BACKEND_URL, { cache: "no-store" });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error?.message || "Failed to reach backend evaluation endpoint" },
      { status: 502 },
    );
  }
}
