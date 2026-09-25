import { SignUp } from "@clerk/nextjs";

/**
 * Sign-Up Page — renders Clerk's pre-built sign-up component.
 *
 * The [[...sign-up]] catch-all route handles Clerk's multi-step flows.
 */
export default function SignUpPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-6 py-12">
      <SignUp
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
