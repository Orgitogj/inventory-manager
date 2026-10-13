import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "inventory_session";
const LOGIN_ROUTE = "/login";

export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.next();
  }

  return NextResponse.redirect(new URL(LOGIN_ROUTE, request.url));
}

export const config = {
  matcher: ["/((?!api/|_next/|login$|favicon.ico$).*)"],
};
