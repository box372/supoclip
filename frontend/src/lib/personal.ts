/**
 * One-person installation flags.
 *
 * `NEXT_PUBLIC_PERSONAL_MODE` is compiled into the client bundle and read by
 * the server, so it must be set at build time (the Docker build passes it in).
 */
export const PERSONAL_MODE = process.env.NEXT_PUBLIC_PERSONAL_MODE === "true";

export const PERSONAL_USER_ID =
  process.env.NEXT_PUBLIC_PERSONAL_USER_ID || "personal-owner";

export const PERSONAL_USER = {
  id: PERSONAL_USER_ID,
  name: "Owner",
  email: "owner@chunkvex.local",
  emailVerified: true as const,
  image: null as string | null,
};

/** Routes that disappear in personal mode: paid plans and multi-user features. */
export const PERSONAL_HIDDEN_ROUTES = [
  "/affiliate",
  "/analytics",
  "/settings/social",
  "/settings/creator-program",
  "/admin",
  "/sign-up",
  "/sign-in",
  "/forgot-password",
  "/reset-password",
] as const;
