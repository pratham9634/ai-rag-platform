import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

/**
 * Landing Page — the first thing users see.
 *
 * If the user is already signed in, redirect to dashboard.
 * Otherwise, show the landing page with sign-in/sign-up CTAs.
 */
export default async function HomePage() {
  const { userId } = await auth();

  if (userId) {
    redirect("/dashboard");
  }

  return (
    <main className="flex flex-1 flex-col items-center justify-center px-6">
      {/* Hero Section */}
      <div className="max-w-3xl text-center space-y-8">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-sm text-indigo-400">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75"></span>
            <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-500"></span>
          </span>
          AI-Powered Document Intelligence
        </div>

        {/* Title */}
        <h1 className="text-5xl font-bold tracking-tight sm:text-6xl">
          <span className="bg-gradient-to-r from-white via-indigo-200 to-indigo-400 bg-clip-text text-transparent">
            Enterprise RAG
          </span>
          <br />
          <span className="text-gray-400">Platform</span>
        </h1>

        {/* Subtitle */}
        <p className="text-lg text-gray-400 leading-relaxed max-w-2xl mx-auto">
          Upload your documents. Ask questions. Get grounded answers with
          citations. Powered by hybrid retrieval, intelligent agents, and
          your own API key.
        </p>

        {/* CTAs */}
        <div className="flex items-center justify-center gap-4">
          <Link
            href="/sign-up"
            className="rounded-lg bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/25 transition-all hover:bg-indigo-500 hover:shadow-indigo-500/30 hover:-translate-y-0.5"
          >
            Get Started Free
          </Link>
          <Link
            href="/sign-in"
            className="rounded-lg border border-gray-700 bg-gray-900 px-6 py-3 text-sm font-semibold text-gray-300 transition-all hover:border-gray-600 hover:text-white hover:-translate-y-0.5"
          >
            Sign In
          </Link>
        </div>

        {/* Feature Grid */}
        <div className="mt-16 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[
            {
              icon: "📄",
              title: "Document RAG",
              desc: "Hybrid retrieval with semantic + lexical search and reranking",
            },
            {
              icon: "🤖",
              title: "Agentic AI",
              desc: "Intelligent agent with tool calling and web search",
            },
            {
              icon: "🔒",
              title: "Enterprise Security",
              desc: "Multi-tenant isolation, RBAC, and BYOK support",
            },
          ].map((feature) => (
            <div
              key={feature.title}
              className="rounded-xl border border-gray-800 bg-gray-900/50 p-6 text-left transition-colors hover:border-gray-700 hover:bg-gray-900"
            >
              <div className="text-2xl mb-3">{feature.icon}</div>
              <h3 className="font-semibold text-white mb-1">{feature.title}</h3>
              <p className="text-sm text-gray-500">{feature.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
