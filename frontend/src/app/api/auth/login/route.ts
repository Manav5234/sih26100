import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const { token, email, password } = body || {};

  const isProduction = process.env.ENVIRONMENT === "production";

  // Case 1: External/Backend JWT token provided -> save in httpOnly cookie
  if (token) {
    const res = NextResponse.json({ ok: true, token });
    res.cookies.set("access_token", token, {
      httpOnly: true,
      secure: isProduction,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 8, // 8 hours
    });
    return res;
  }

  // Case 2: Direct credential login fallback (for Vercel standalone frontend deployments)
  if (email && password) {
    const cleanEmail = String(email).trim().toLowerCase();
    if (cleanEmail === "priya@example.gov.in" && password === "secret123") {
      const demoToken = "demo_officer_token_priya_sharma";
      const res = NextResponse.json({
        ok: true,
        token: demoToken,
        officer: { id: "00000000-0000-0000-0000-000000000001", role: "INSPECTOR" },
      });
      res.cookies.set("access_token", demoToken, {
        httpOnly: true,
        secure: isProduction,
        sameSite: "lax",
        path: "/",
        maxAge: 60 * 60 * 8,
      });
      return res;
    }

    return NextResponse.json(
      { error: "Invalid officer credentials. Please verify email and password." },
      { status: 401 }
    );
  }

  return NextResponse.json({ error: "missing token or credentials" }, { status: 400 });
}
