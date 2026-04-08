"use client";

import { useState } from "react";
import { useCompletion } from "@ai-sdk/react";

export default function Page() {
  const [text, setText] = useState("");
  const [validationError, setValidationError] = useState("");
  const {
    completion,
    complete,
    isLoading,
    error,
    setCompletion,
  } = useCompletion({
    api: "/api/summarize",
    streamProtocol: "text",
  });

  function handleSubmit() {
    setValidationError("");
    const trimmed = text.trim();
    if (!trimmed) {
      setValidationError("Please enter some text to summarize.");
      return;
    }
    setCompletion("");
    complete(trimmed);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSubmit();
    }
  }

  const displayError = validationError || error?.message;

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-2xl flex-col gap-6 py-16 px-8">
        <h1 className="text-xl font-semibold text-black dark:text-zinc-50">
          Text Summarizer
        </h1>

        <label htmlFor="text-input" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Input text
        </label>
        <textarea
          id="text-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Enter or paste text to summarize..."
          rows={6}
          disabled={isLoading}
          className="w-full rounded border border-zinc-300 px-3 py-2 text-zinc-900 disabled:opacity-60 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
        />

        <button
          type="button"
          onClick={handleSubmit}
          disabled={isLoading}
          className="w-fit rounded bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {isLoading ? "Generating..." : "Generate Summary"}
        </button>
        {isLoading && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400" aria-live="polite">
            Generating...
          </p>
        )}

        {displayError && (
          <div
            role="alert"
            className="rounded border border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-400 dark:bg-red-950 dark:text-red-300"
          >
            {displayError}
          </div>
        )}

        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Summary
          </label>
          <div className="min-h-[4rem] rounded border border-zinc-300 bg-zinc-50 px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100">
            {completion || "—"}
          </div>
        </div>
      </main>
    </div>
  );
}
