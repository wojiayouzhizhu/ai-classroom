"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import WelcomeModal from "@/components/WelcomeModal";

const SUGGESTIONS = [
  "Explain recursion",
  "How does a hash table work?",
  "What is Big O notation?",
  "Explain binary search",
  "What are linked lists?",
];

export default function LandingPage() {
  const router = useRouter();
  const [provider, setProvider] = useState<"groq" | "gemini">("groq");
  const [hoveredSuggestion, setHoveredSuggestion] = useState<string | null>(null);

  function startChat(prefill?: string) {
    const params = new URLSearchParams();
    params.set("provider", provider);
    if (prefill) params.set("q", prefill);
    router.push(`/chat?${params.toString()}`);
  }

  return (
    <main className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center px-6 py-16">
      <WelcomeModal />
      {/* Title */}
      <div className="text-center mb-12 animate-fade-in">
        <p className="text-zinc-500 text-xs tracking-[0.3em] uppercase mb-4">
          AI-Powered Learning
        </p>
        <h1 className="text-5xl font-bold text-white tracking-tight mb-4">
          CS Tutor
        </h1>
        <p className="text-zinc-400 text-lg max-w-md mx-auto leading-relaxed">
          Learn by thinking, not copying. A Socratic tutor that guides you
          toward answers instead of giving them away.
        </p>
      </div>

      {/* Provider selector */}
      <div className="mb-10 w-full max-w-sm">
        <p className="text-zinc-500 text-xs text-center mb-3 tracking-widest uppercase">
          Choose your AI
        </p>
        <div className="grid grid-cols-2 gap-3">
          {(["groq", "gemini"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setProvider(p)}
              className={`py-3 px-4 rounded-xl border text-sm font-medium transition-all ${
                provider === p
                  ? "border-white text-white bg-white/10"
                  : "border-zinc-800 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300"
              }`}
            >
              {p === "groq" ? "⚡ Groq" : "✦ Gemini"}
            </button>
          ))}
        </div>
      </div>

      {/* Suggestions */}
      <div className="mb-10 w-full max-w-lg">
        <p className="text-zinc-500 text-xs text-center mb-3 tracking-widest uppercase">
          Try one of these
        </p>
        <div className="flex flex-wrap gap-2 justify-center">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => startChat(s)}
              onMouseEnter={() => setHoveredSuggestion(s)}
              onMouseLeave={() => setHoveredSuggestion(null)}
              className={`text-xs px-4 py-2 rounded-full border transition-all ${
                hoveredSuggestion === s
                  ? "border-zinc-400 text-zinc-200 bg-zinc-800"
                  : "border-zinc-700 text-zinc-400"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Start button */}
      <button
        onClick={() => startChat()}
        className="px-8 py-3 rounded-xl bg-white text-zinc-950 text-sm font-semibold hover:bg-zinc-200 transition-colors mb-16"
      >
        Start Chatting →
      </button>

      {/* About */}
      <div className="border-t border-zinc-800 pt-10 w-full max-w-lg text-center">
        <p className="text-zinc-500 text-xs tracking-widest uppercase mb-4">
          About
        </p>
        <p className="text-zinc-400 text-sm leading-relaxed">
          Built with FastAPI, LangGraph, and Next.js. Uses a multi-node state
          machine to track understanding, escalate hints, and execute code via
          Judge0. Supports PDF upload for personalized RAG-based tutoring.
        </p>
        <div className="flex gap-4 justify-center mt-6">
          <a
            href="https://github.com/RipClaw15/Tutor-Chatbot"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            GitHub →
          </a>
        </div>
      </div>

    </main>
  );
}
