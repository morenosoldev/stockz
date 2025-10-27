import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  toolName?: string;
  timestamp: string;
}

export interface Conversation {
  id: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
}

interface ChatStore {
  // Current conversation
  currentConversationId: string | null;
  conversations: Record<string, Conversation>;

  // Actions
  startNewConversation: () => string;
  addMessage: (conversationId: string, message: Omit<Message, 'id' | 'timestamp'>) => void;
  clearConversation: (conversationId: string) => void;
  deleteConversation: (conversationId: string) => void;
  setCurrentConversation: (conversationId: string | null) => void;

  // Helpers
  getCurrentConversation: () => Conversation | null;
}

/**
 * Zustand store for chat state management with localStorage persistence.
 */
export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      currentConversationId: null,
      conversations: {},

      startNewConversation: () => {
        const id = `conv_${Date.now()}`;
        const conversation: Conversation = {
          id,
          messages: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };

        set((state) => ({
          conversations: {
            ...state.conversations,
            [id]: conversation,
          },
          currentConversationId: id,
        }));

        return id;
      },

      addMessage: (conversationId, message) => {
        const newMessage: Message = {
          ...message,
          id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          timestamp: new Date().toISOString(),
        };

        set((state) => {
          const conversation = state.conversations[conversationId];
          if (!conversation) return state;

          return {
            conversations: {
              ...state.conversations,
              [conversationId]: {
                ...conversation,
                messages: [...conversation.messages, newMessage],
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      clearConversation: (conversationId) => {
        set((state) => {
          const conversation = state.conversations[conversationId];
          if (!conversation) return state;

          return {
            conversations: {
              ...state.conversations,
              [conversationId]: {
                ...conversation,
                messages: [],
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      deleteConversation: (conversationId) => {
        set((state) => {
          // eslint-disable-next-line @typescript-eslint/no-unused-vars
          const { [conversationId]: _deleted, ...rest } = state.conversations;
          return {
            conversations: rest,
            currentConversationId:
              state.currentConversationId === conversationId
                ? null
                : state.currentConversationId,
          };
        });
      },

      setCurrentConversation: (conversationId) => {
        set({ currentConversationId: conversationId });
      },

      getCurrentConversation: () => {
        const state = get();
        if (!state.currentConversationId) return null;
        return state.conversations[state.currentConversationId] || null;
      },
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        conversations: state.conversations,
        currentConversationId: state.currentConversationId,
      }),
    }
  )
);
