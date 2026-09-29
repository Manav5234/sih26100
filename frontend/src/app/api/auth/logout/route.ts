import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const acceptHeader = req.headers.get("accept") || "";
  const isFetch = acceptHeader.includes("application/json");

  const loginUrl = new URL("/login", req.url);
  const res = isFetch
    ? NextResponse.json({ ok: true, redirect: "/login" })
    : NextResponse.redirect(loginUrl, 303);

  res.cookies.set("access_token", "", {
    httpOnly: true,
    maxAge: 0,
    path: "/",
  });

  return res;
}

