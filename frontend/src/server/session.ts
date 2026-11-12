import { headers } from "next/headers";

import { auth } from "@/lib/auth";
import { PERSONAL_MODE, PERSONAL_USER } from "@/lib/personal";

/**
 * The signed-in session for the current request.
 *
 * In personal mode there is no login: the single owner is always signed in and
 * the backend is called with that fixed user id. Everywhere else this is the
 * Better Auth session from the request cookies.
 */
export async function getServerSession() {
  if (PERSONAL_MODE) {
    const now = new Date();
    return {
      user: { ...PERSONAL_USER, createdAt: now, updatedAt: now },
      session: {
        id: "personal-session",
        token: "personal-session",
        userId: PERSONAL_USER.id,
        expiresAt: new Date(now.getTime() + 365 * 24 * 60 * 60 * 1000),
        createdAt: now,
        updatedAt: now,
        ipAddress: null,
        userAgent: null,
      },
    } as unknown as Awaited<ReturnType<typeof auth.api.getSession>>;
  }
  return auth.api.getSession({ headers: await headers() });
}
