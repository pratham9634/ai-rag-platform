import { UserButton } from "@clerk/nextjs";
import { currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

/**
 * Dashboard Page — the main authenticated view.
 *
 * This is a protected route (middleware.ts redirects unauthenticated users).
 * Currently a stub — will be expanded with:
 *   - Document list
 *   - Upload widget
 *   - Chat interface
 *   - BYOK settings
 *   - Usage stats
 */
export default async function DashboardPage() {
  const user = await currentUser();

  if (!user) {
    redirect("/sign-in");
  }

  return (
    <div className="flex flex-1 flex-col">
      {/* Top Navigation */}
      <header className="flex items-center justify-between border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm px-6 py-4">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-white">
            Enterprise RAG
          </h1>
          <span className="rounded-full bg-indigo-500/10 border border-indigo-500/30 px-2.5 py-0.5 text-xs text-indigo-400">
            Beta
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-400">
            {user.firstName || user.emailAddresses[0]?.emailAddress}
          </span>
          <UserButton
            appearance={{
              elements: {
                avatarBox: "h-8 w-8",
              },
            }}
          />
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 px-6 py-8">
        <div className="max-w-5xl mx-auto space-y-8">
          {/* Welcome Section */}
          <div>
            <h2 className="text-2xl font-bold text-white">
              Welcome, {user.firstName || "there"} 👋
            </h2>
            <p className="mt-1 text-gray-400">
              Your AI-powered document intelligence platform is ready.
            </p>
          </div>

          {/* Status Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                label: "Documents",
                value: "0 / 3",
                icon: "📄",
                detail: "Upload limit",
              },
              {
                label: "API Key",
                value: "Not set",
                icon: "🔑",
                detail: "Configure BYOK",
              },
              {
                label: "Model",
                value: "—",
                icon: "🤖",
                detail: "Select model",
              },
              {
                label: "Retention",
                value: "7 days",
                icon: "⏱️",
                detail: "Auto-cleanup",
              },
            ].map((card) => (
              <div
                key={card.label}
                className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 transition-colors hover:border-gray-700"
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm text-gray-500">{card.label}</span>
                  <span className="text-xl">{card.icon}</span>
                </div>
                <p className="text-lg font-semibold text-white">{card.value}</p>
                <p className="text-xs text-gray-600 mt-1">{card.detail}</p>
              </div>
            ))}
          </div>

          {/* Placeholder Sections */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Chat */}
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6 min-h-[300px] flex flex-col items-center justify-center text-center">
              <div className="text-4xl mb-4">💬</div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Chat with Documents
              </h3>
              <p className="text-sm text-gray-500 max-w-xs">
                Upload documents and start asking questions. Answers will be
                grounded in your uploaded content with citations.
              </p>
              <span className="mt-4 rounded-full bg-gray-800 px-3 py-1 text-xs text-gray-500">
                Coming in Day 4
              </span>
            </div>

            {/* Documents */}
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6 min-h-[300px] flex flex-col items-center justify-center text-center">
              <div className="text-4xl mb-4">📁</div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Document Library
              </h3>
              <p className="text-sm text-gray-500 max-w-xs">
                Upload, manage, and track your documents. Each document is
                automatically parsed, chunked, and indexed.
              </p>
              <span className="mt-4 rounded-full bg-gray-800 px-3 py-1 text-xs text-gray-500">
                Coming in Day 2
              </span>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
