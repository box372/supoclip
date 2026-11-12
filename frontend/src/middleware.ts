import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { PERSONAL_HIDDEN_ROUTES } from "@/lib/personal";

const PUBLIC_FILE = /\.(.*)$/;
// Read directly here: the edge runtime only sees environment variables that
// are statically referenced in this file (a constant imported from another
// module is not inlined).
const personalMode =
  process.env.NEXT_PUBLIC_PERSONAL_MODE === "true" ||
  process.env.PERSONAL_MODE === "true";

export function middleware(request: NextRequest) {
  const isLandingOnlyModeEnabled =
    process.env.NEXT_PUBLIC_LANDING_ONLY_MODE === "true";

  // Personal mode: paid plans, social publishing, analytics and accounts are
  // not part of a one-person installation. Send those URLs home.
  if (personalMode) {
    const { pathname } = request.nextUrl;
    const hidden = PERSONAL_HIDDEN_ROUTES.some(
      (route) => pathname === route || pathname.startsWith(`${route}/`),
    );
    if (hidden) {
      const url = request.nextUrl.clone();
      url.pathname = "/";
      url.search = "";
      return NextResponse.redirect(url);
    }
  }

  if (!isLandingOnlyModeEnabled) {
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;

  if (
    pathname === "/" ||
    pathname === "/status" ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api/billing/webhook") ||
    pathname.startsWith("/ingest/") ||
    // Opt-outs (including mailbox one-click POSTs) must work in every mode.
    pathname === "/email/product-updates/unsubscribe" ||
    PUBLIC_FILE.test(pathname)
  ) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api")) {
    return NextResponse.json(
      { error: "SupoClip is in landing-page-only mode." },
      { status: 503 }
    );
  }

  const url = request.nextUrl.clone();
  url.pathname = "/";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  matcher: "/:path*",
};
