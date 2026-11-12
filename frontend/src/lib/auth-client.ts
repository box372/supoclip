import { createAuthClient } from "better-auth/react";
import { useSyncExternalStore } from "react";

import { PERSONAL_MODE, PERSONAL_USER } from "@/lib/personal";

export const authClient = createAuthClient();

export const { signIn, signOut, signUp, requestPasswordReset, resetPassword } = authClient;

const subscribeToHydration = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

export function useSession(...args: Parameters<typeof authClient.useSession>) {
  const session = authClient.useSession(...args);
  const hydrated = useSyncExternalStore(subscribeToHydration, clientSnapshot, serverSnapshot);

  // Personal mode has no login: the single owner is always signed in.
  if (PERSONAL_MODE) {
    const now = new Date();
    return {
      ...session,
      data: {
        user: { ...PERSONAL_USER, createdAt: now, updatedAt: now },
        session: {
          id: "personal-session",
          token: "personal-session",
          userId: PERSONAL_USER.id,
          expiresAt: new Date(now.getTime() + 365 * 24 * 60 * 60 * 1000),
          createdAt: now,
          updatedAt: now,
        },
      },
      isPending: false,
    } as unknown as typeof session;
  }

  // A sibling can resolve the shared auth store before this component hydrates.
  // Match the server's loading state until this consumer finishes hydration.
  return hydrated ? session : { ...session, data: null, isPending: true };
}
