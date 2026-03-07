"use client";

import { useState, useRef } from "react";
import { useChatStore } from "../core/store/useChatStore";
import type { Workspace } from "../core/types/api";

export default function CommandCenter({ workspace }: { workspace: Workspace }) {
  const isPending = useChatStore((state) => state.isPending[workspace]);
  const sendMessage = useChatStore((state) => state.sendMessage);
  const uploadCV = useChatStore((state) => state.uploadCV);
  const [inputText, setInputText] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const placeholder =
    workspace === "profile"
      ? "Discuss your background or upload a CV..."
      : "Ask Navigator to refine search...";

  const paddingClass = workspace === "profile" ? "pl-10" : "pl-4";

  const handleSend = () => {
    if (!inputText.trim() || isPending) return;
    sendMessage(inputText, workspace);
    setInputText("");
  };

  const handleFileClick = () => {
    fileInputRef.current?.click();
  };

  const resetFileInput = () => {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || isPending) return;
    uploadCV(file);
    resetFileInput();
  };

  return (
    <div className="p-4 border-t border-glass-border bg-surface-dark/95 backdrop-blur-xl">
      <div className="relative flex items-center">
        {/* Hidden File Input — only wired in Profile workspace */}
        {workspace === "profile" && (
          <>
            <input
              type="file"
              accept="application/pdf"
              data-testid="cv-file-input"
              ref={fileInputRef}
              onChange={handleFileChange}
              className="hidden"
              disabled={isPending}
            />

            {/* Attachment Button */}
            <button
              onClick={handleFileClick}
              disabled={isPending}
              className="absolute left-3 text-slate-400 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Attach CV (PDF)"
            >
              <span className="material-symbols-outlined text-[20px]">
                attach_file
              </span>
            </button>
          </>
        )}

        {/* Message Input */}
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          disabled={isPending}
          placeholder={placeholder}
          className={`w-full bg-background-dark/50 border border-glass-border rounded-xl py-3 pr-12 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-primary/50 focus:border-primary/50 transition-all disabled:opacity-70 ${paddingClass}`}
        />

        {/* Send Button */}
        <button
          onClick={handleSend}
          disabled={isPending || !inputText.trim()}
          aria-label="Send message"
          title="Send message"
          className="absolute right-2 p-1.5 bg-primary hover:bg-primary-hover text-white rounded-lg transition-colors flex items-center justify-center shadow-lg shadow-primary/20 disabled:opacity-50 disabled:bg-slate-700 disabled:shadow-none"
        >
          {isPending ? (
            <span className="material-symbols-outlined text-[18px] animate-spin">
              progress_activity
            </span>
          ) : (
            <span className="material-symbols-outlined text-[18px]">
              arrow_upward
            </span>
          )}
        </button>
      </div>

      {/* Help Text / Status */}
      <div className="mt-2 flex justify-between items-center px-2">
        <span className="text-[10px] text-slate-500 font-medium">
          {isPending ? "Agent is processing..." : "Ready to assist"}
        </span>
        <span className="text-[10px] text-slate-600">Press Enter to send</span>
      </div>
    </div>
  );
}
