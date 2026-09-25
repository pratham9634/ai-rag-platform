/**
 * Clerk Middleware — Protects routes that require authentication.
 *
 * How it works:
 *   1. Every request passes through this middleware
 *   2. clerkMiddleware() checks if the user has a valid session
 *   3. Public routes (sign-in, sign-up, home) are accessible without auth
 *   4. Protected routes (dashboard, chat) redirect to sign-in
 *
 * Why middleware instead of per-page checks?
 *   - Centralized auth gate — one place to define public vs protected routes
 *   - Runs on the Edge — fast, before page rendering
 *   - Cannot be bypassed by client-side navigation
 */
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
]);

export default clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
  ],
};
