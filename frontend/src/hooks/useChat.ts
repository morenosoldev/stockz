import { useMutation } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import { useChatStore } from '@/stores/chatStore';
import { useScanStore } from '@/stores/scanStore';

interface UseChatOptions {
  onSuccess?: (message: string) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook for sending chat messages to the AI assistant.
 * Integrates with React Query for API calls and Zustand for state management.
 */
export function useChat({ onSuccess, onError }: UseChatOptions = {}) {
  const { currentConversationId, addMessage, startNewConversation, getCurrentConversation } =
    useChatStore();
  const { openModal } = useScanStore();

  const mutation = useMutation({
    mutationFn: async (message: string) => {
      // Ensure we have a conversation
      const conversationId = currentConversationId || startNewConversation();

      // Add user message to store
      addMessage(conversationId, {
        role: 'user',
        content: message,
      });

      // Call API
      const { data, error } = await apiClient.POST('/v1/chat', {
        body: {
          message,
          conversation_id: conversationId,
        },
      });

      if (error) {
        throw new Error(
          // @ts-expect-error - error structure may vary
          error?.detail || error?.message || 'Failed to send message'
        );
      }

      return { data, conversationId };
    },
    onSuccess: ({ data, conversationId }) => {
      if (!data) return;

      // Add assistant response to store
      addMessage(conversationId, {
        role: 'assistant',
        content: data.message,
      });

      // Add tool calls as separate messages
      if (data.tool_calls && data.tool_calls.length > 0) {
        data.tool_calls.forEach((toolCall) => {
          addMessage(conversationId, {
            role: 'tool',
            content: JSON.stringify(toolCall.result, null, 2),
            toolName: toolCall.tool,
          });

          // Check if tool call is for market scan
          if (
            toolCall.tool === 'scan_market' &&
            toolCall.result &&
            typeof toolCall.result === 'object'
          ) {
            // Backend returns run_ids array, get the first one
            const result = toolCall.result as { run_ids?: string[]; run_id?: string };
            const runId = result.run_ids?.[0] || result.run_id;

            if (runId) {
              console.log('Scan triggered, opening modal with run_id:', runId);
              openModal(runId);
            } else {
              console.warn('Scan triggered but no run_id found in result:', toolCall.result);
            }
          }
        });
      }

      onSuccess?.(data.message);
    },
    onError: (error: Error) => {
      console.error('Chat error:', error);
      onError?.(error);
    },
  });

  return {
    sendMessage: mutation.mutate,
    isLoading: mutation.isPending,
    error: mutation.error,
    conversation: getCurrentConversation(),
  };
}
