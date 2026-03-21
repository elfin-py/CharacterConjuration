import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = "http://127.0.0.1:8000/fill_sheet_official";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const res = await fetch(BACKEND_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const errText = await res.text();
      return NextResponse.json({ error: errText }, { status: res.status });
    }

    const arrayBuffer = await res.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": "attachment; filename=character_sheet.pdf",
      },
    });
  } catch (err) {
    console.error("Error proxying fill_sheet:", err);
    return NextResponse.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
