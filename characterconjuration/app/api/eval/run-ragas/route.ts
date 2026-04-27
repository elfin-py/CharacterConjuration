import { NextResponse } from "next/server";

const BACKEND_URL = "http://127.0.0.1:8000/eval/run_ragas";

export async function POST() {
  try {
    const res = await fetch(BACKEND_URL, { method: "POST", cache: "no-store" });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error?.message || "Failed to trigger backend RAGAS evaluation" },
      { status: 502 },
    );
  }
}
