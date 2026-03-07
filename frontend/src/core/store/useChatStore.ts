import { create } from "zustand";
import { ChatResponse, Workspace } from "../types/api";
import {
  fetchHistoryRequest,
  sendMessageRequest,
  uploadCVRequest,
} from "../api/chat";
import { useJobStore } from "./useJobStore";

/** Placeholder shown in the thread while the AI response is in-flight. */
export const PENDING_AI_MESSAGE = "...";

export interface ChatState {
  threads: Record<Workspace, ChatResponse[]>;
  isPending: Record<Workspace, boolean>;
  fetchHistory: (workspace: Workspace) => Promise<void>;
  sendMessage: (text: string, workspace: Workspace) => Promise<void>;
  uploadCV: (file: File) => Promise<void>;
}

export const useChatStore = create<ChatState>((set) => ({
  threads: { discovery: [], profile: [] },
  isPending: { discovery: false, profile: false },

  fetchHistory: async (workspace: Workspace) => {
    set((state) => ({ isPending: { ...state.isPending, [workspace]: true } }));
    try {
      const history = await fetchHistoryRequest(workspace);
      set((state) => ({ threads: { ...state.threads, [workspace]: history } }));
    } catch (error) {
      console.error("Failed to fetch history:", error);
    } finally {
      set((state) => ({
        isPending: { ...state.isPending, [workspace]: false },
      }));
    }
  },

  sendMessage: async (text: string, workspace: Workspace) => {
    const optimisticMsg: ChatResponse = {
      user_message: text,
      ai_message: PENDING_AI_MESSAGE,
      jobs: [],
    };

    set((state) => ({
      threads: {
        ...state.threads,
        [workspace]: [...state.threads[workspace], optimisticMsg],
      },
      isPending: { ...state.isPending, [workspace]: true },
    }));

    try {
      const response = await sendMessageRequest(text, workspace);
      set((state) => {
        const thread = [...state.threads[workspace]];
        thread[thread.length - 1] = response;
        return { threads: { ...state.threads, [workspace]: thread } };
      });

      if (response.jobs && response.jobs.length > 0) {
        await useJobStore.getState().fetchDeck();
      }
    } catch (error) {
      console.error("Failed to send message:", error);
      set((state) => {
        const thread = [...state.threads[workspace]];
        thread[thread.length - 1] = {
          user_message: text,
          ai_message: `**System Error**: Failed to communicate with server.`,
          jobs: [],
        };
        return { threads: { ...state.threads, [workspace]: thread } };
      });
    } finally {
      set((state) => ({
        isPending: { ...state.isPending, [workspace]: false },
      }));
    }
  },

  uploadCV: async (file: File) => {
    const optimisticMsg: ChatResponse = {
      user_message: `Uploaded CV: ${file.name}`,
      ai_message: PENDING_AI_MESSAGE,
      jobs: [],
    };

    set((state) => ({
      threads: {
        ...state.threads,
        profile: [...state.threads.profile, optimisticMsg],
      },
      isPending: { ...state.isPending, profile: true },
    }));

    try {
      const response = await uploadCVRequest(file);
      set((state) => {
        const thread = [...state.threads.profile];
        thread[thread.length - 1] = response;
        return { threads: { ...state.threads, profile: thread } };
      });
    } catch (error) {
      console.error("Failed to upload CV:", error);
      set((state) => {
        const thread = [...state.threads.profile];
        thread[thread.length - 1] = {
          user_message: `Uploaded CV: ${file.name}`,
          ai_message: `**System Error**: Failed to process CV.`,
          jobs: [],
        };
        return { threads: { ...state.threads, profile: thread } };
      });
    } finally {
      set((state) => ({ isPending: { ...state.isPending, profile: false } }));
    }
  },
}));
