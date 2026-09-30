import { NextRequest, NextResponse } from "next/server";

/**
 * Auth cookie route — stores the real JWT from FastAPI backend.
 *
 * SECURITY: This route only accepts a token that was already validated by the
 * FastAPI backend. It does NOT perform its own credential validation.
 * The fake "demo_officer_token_priya_sharma" fallback has been removed.
 * If the backend is unreachable, login fails — do not grant frontend-only auth.
 */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const { token } = body || {};

  const isProduction = process.env.ENVIRONMENT === "production";

  // Only accept a real backend-issued JWT token
  if (token && typeof token === "string" && token.length > 10) {
    const res = NextResponse.json({ ok: true });
    res.cookies.set("access_token", token, {
      httpOnly: true,
      secure: isProduction,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 8, // 8 hours — matches backend JWT expiry
    });
    return res;
  }

  return NextResponse.json(
    { error: "A valid backend JWT token is required. Please authenticate via the FastAPI backend." },
    { status: 400 }
  );
}
