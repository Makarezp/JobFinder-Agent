"use client";

import { useEffect, useState, useRef } from "react";
import { useChatStore } from "../core/store/useChatStore";

export default function Home() {
  const { messages, isPending, fetchHistory, sendMessage, uploadCV } =
    useChatStore();
  const [inputText, setInputText] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isMounted, setIsMounted] = useState(false);

  // Hydrate history on mount and avoid SSR hydration mismatch
  useEffect(() => {
    setIsMounted(true);
    fetchHistory();
  }, [fetchHistory]);

  if (!isMounted) {
    return <main style={{ padding: "2rem", fontFamily: "sans-serif" }}><h1>Loading...</h1></main>;
  }

  const handleSend = () => {
    if (!inputText.trim() || isPending) return;
    sendMessage(inputText);
    setInputText("");
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || isPending) return;
    uploadCV(file);
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <main style={{ padding: "2rem", fontFamily: "sans-serif" }}>
      <h1>CVviewer Setup Check (Sprint 0)</h1>

      <div
        style={{
          border: "1px solid #ccc",
          padding: "1rem",
          height: "400px",
          overflowY: "auto",
          marginBottom: "1rem",
        }}
      >
        {messages.length === 0 ? (
          <p style={{ color: "gray" }}>No messages yet.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0 }}>
            {messages.map((msg, idx) => (
              <li key={idx} style={{ marginBottom: "1rem" }}>
                <div>
                  <strong>User:</strong> {msg.user_message}
                </div>
                <div style={{ marginTop: "0.5rem" }}>
                  <strong>AI:</strong> {msg.ai_message}
                </div>
                {msg.jobs && msg.jobs.length > 0 && (
                  <div style={{ marginTop: "0.5rem", fontSize: "0.9em" }}>
                    <em>Found {msg.jobs.length} jobs.</em>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {isPending && <p><em>Agent is typing...</em></p>}
      </div>

      <div style={{ display: "flex", gap: "0.5rem" }}>
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSend();
          }}
          disabled={isPending}
          placeholder="Type a message..."
          style={{ flex: 1, padding: "0.5rem" }}
        />
        <button
          onClick={handleSend}
          disabled={isPending || !inputText.trim()}
          style={{ padding: "0.5rem 1rem" }}
        >
          Send
        </button>

        <input
          type="file"
          accept="application/pdf"
          onChange={handleFileChange}
          disabled={isPending}
          ref={fileInputRef}
          style={{ padding: "0.5rem" }}
        />
      </div>
    </main>
  );
}
