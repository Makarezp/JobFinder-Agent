import { create } from "zustand";
import { ChatResponse } from "../types/api";
import {
  fetchHistoryRequest,
  sendMessageRequest,
  uploadCVRequest,
} from "../api/chat";

interface ChatState {
  messages: ChatResponse[];
  isPending: boolean;
  fetchHistory: () => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  uploadCV: (file: File) => Promise<void>;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isPending: false,

  fetchHistory: async () => {
    try {
      set({ isPending: true });
      const history = await fetchHistoryRequest();
      set({ messages: history });
    } catch (error) {
      console.error("Failed to fetch history:", error);
    } finally {
      set({ isPending: false });
    }
  },

  sendMessage: async (text: string) => {
    // Optimistic UI update
    const optimisticMsg: ChatResponse = {
      user_message: text,
      ai_message: "...", // Loading indicator
      jobs: [],
    };

    set((state) => ({
      messages: [...state.messages, optimisticMsg],
      isPending: true,
    }));

    try {
      const response = await sendMessageRequest(text);
      set((state) => {
        // Replace the optimistic message with the actual response
        const newMessages = [...state.messages];
        newMessages[newMessages.length - 1] = response;
        return { messages: newMessages };
      });
    } catch (error) {
      console.error("Failed to send message:", error);
      set((state) => {
        const newMessages = [...state.messages];
        newMessages[newMessages.length - 1] = {
          user_message: text,
          ai_message: `**System Error**: Failed to communicate with server.`,
          jobs: [],
        };
        return { messages: newMessages };
      });
    } finally {
      set({ isPending: false });
    }
  },

  uploadCV: async (file: File) => {
    const optimisticMsg: ChatResponse = {
      user_message: `Uploaded CV: ${file.name}`,
      ai_message: "Processing CV...",
      jobs: [],
    };

    set((state) => ({
      messages: [...state.messages, optimisticMsg],
      isPending: true,
    }));

    try {
      const response = await uploadCVRequest(file);
      set((state) => {
        const newMessages = [...state.messages];
        newMessages[newMessages.length - 1] = response;
        return { messages: newMessages };
      });
    } catch (error) {
      console.error("Failed to upload CV:", error);
      set((state) => {
        const newMessages = [...state.messages];
        newMessages[newMessages.length - 1] = {
          user_message: `Uploaded CV: ${file.name}`,
          ai_message: `**System Error**: Failed to process CV.`,
          jobs: [],
        };
        return { messages: newMessages };
      });
    } finally {
      set({ isPending: false });
    }
  },
}));
