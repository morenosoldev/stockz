import { useEffect, useRef } from 'react';
import { Loader2, MessageSquare, Plus } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { useChat } from '@/hooks/useChat';
import { useChatStore } from '@/stores/chatStore';

/**
 * Chat sidebar component with AI assistant integration.
 * Displays conversation history and allows sending messages.
 */
export function ChatSidebar() {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { startNewConversation, getCurrentConversation } = useChatStore();
  const conversation = getCurrentConversation();

  const { sendMessage, isLoading } = useChat({
    onSuccess: () => {
      // Auto-scroll to bottom on new message
      scrollToBottom();
    },
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Auto-scroll when messages change
  useEffect(() => {
    scrollToBottom();
  }, [conversation?.messages]);

  // Create initial conversation if none exists
  useEffect(() => {
    if (!conversation) {
      startNewConversation();
    }
  }, [conversation, startNewConversation]);

  const handleSendMessage = (message: string) => {
    sendMessage(message);
  };

  const handleNewConversation = () => {
    startNewConversation();
  };

  return (
    <aside className="w-96 border-l border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 flex flex-col">
      {/* Chat Header */}
      <div className="border-b border-gray-200 dark:border-gray-800 p-4 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-primary-500" />
            <h3 className="font-semibold text-gray-900 dark:text-white">AI Assistant</h3>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Ask me to scan the market
          </p>
        </div>
        <button
          onClick={handleNewConversation}
          className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          title="New conversation"
        >
          <Plus className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        </button>
      </div>

      {/* Chat Messages */}
      <div className="flex-1 overflow-auto p-4">
        {conversation?.messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <MessageSquare className="w-12 h-12 text-gray-300 dark:text-gray-700 mb-4" />
            <p className="text-gray-900 dark:text-gray-100 font-medium mb-2">
              Welcome to Recover-Bot!
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              I can help you scan the market for recovery candidates. Try asking:
            </p>
            <div className="space-y-2 text-left w-full max-w-xs">
              <button
                onClick={() => handleSendMessage('scan the market')}
                className="w-full text-left px-4 py-2 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg text-sm transition-colors"
              >
                • "scan the market"
              </button>
              <button
                onClick={() => handleSendMessage('show me today\'s candidates')}
                className="w-full text-left px-4 py-2 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg text-sm transition-colors"
              >
                • "show me today's candidates"
              </button>
              <button
                onClick={() => handleSendMessage('explain the drop5 strategy')}
                className="w-full text-left px-4 py-2 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg text-sm transition-colors"
              >
                • "explain the drop5 strategy"
              </button>
            </div>
          </div>
        ) : (
          <>
            {conversation?.messages.map((message) => (
              <ChatMessage
                key={message.id}
                role={message.role}
                content={message.content}
                toolName={message.toolName}
                timestamp={message.timestamp}
              />
            ))}
            {isLoading && (
              <div className="flex justify-start mb-4">
                <div className="flex gap-2 max-w-[85%]">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 bg-gray-200 dark:bg-gray-700">
                    <Loader2 className="w-4 h-4 animate-spin text-gray-700 dark:text-gray-300" />
                  </div>
                  <div className="bg-gray-100 dark:bg-gray-800 rounded-lg px-4 py-2">
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      Thinking...
                    </p>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Chat Input */}
      <ChatInput
        onSend={handleSendMessage}
        disabled={isLoading}
        placeholder={isLoading ? 'Waiting for response...' : 'Type a message...'}
      />
    </aside>
  );
}
