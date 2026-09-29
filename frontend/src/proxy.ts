import { NextRequest, NextResponse } from "next/server";

// Protected routes requiring Procurement Officer session
const protectedPaths = ["/tenders", "/dashboard", "/bidders", "/audit", "/settings"];

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const isProtected = protectedPaths.some((p) => pathname.startsWith(p));
  if (!isProtected) return NextResponse.next();

  const token = req.cookies.get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login", req.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/tenders/:path*",
    "/dashboard/:path*",
    "/bidders/:path*",
    "/audit/:path*",
    "/settings/:path*",
  ],
};
