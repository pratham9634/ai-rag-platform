import { SignIn } from "@clerk/nextjs";

/**
 * Sign-In Page — renders Clerk's pre-built sign-in component.
 *
 * Why Clerk's component instead of a custom form?
 *   - Handles password hashing, rate limiting, CSRF, brute-force protection
 *   - Supports OAuth, MFA, email verification out of the box
 *   - Maintained by Clerk's security team
 *   - We focus on our RAG features, not auth UX
 *
 * The [[...sign-in]] catch-all route handles Clerk's multi-step flows
 * (e.g., MFA verification, email confirmation).
 */
export default function SignInPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-6 py-12">
      <SignIn
        appearance={{
          elements: {
            rootBox: "mx-auto",
            card: "bg-gray-900 border border-gray-800",
          },
        }}
      />
    </main>
  );
}
