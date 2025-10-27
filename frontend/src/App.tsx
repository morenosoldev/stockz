import { useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { useDarkMode } from './hooks/useDarkMode';
import { ChatSidebar } from './components/ChatSidebar';
import { CandidatesGrid } from './components/CandidatesGrid';
import { CandidateDetailModal } from './components/CandidateDetailModal';
import { ScanModal } from './components/ScanModal';

function App() {
  const { theme, toggleTheme } = useDarkMode();
  const [selectedCandidate, setSelectedCandidate] = useState<{
    ticker: string;
    asof: string;
    strategy: string;
  } | null>(null);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors">
      {/* Header */}
      <header className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950">
        <div className="px-6 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 bg-primary-500 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-lg">R</span>
            </div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">
              Recover-Bot
            </h1>
          </div>

          {/* Dark mode toggle */}
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            aria-label="Toggle dark mode"
          >
            {theme === 'light' ? (
              <Moon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            ) : (
              <Sun className="w-5 h-5 text-gray-400" />
            )}
          </button>
        </div>
      </header>

      {/* Main Layout */}
      <div className="flex h-[calc(100vh-73px)]">
        {/* Main Content Area */}
        <main className="flex-1 overflow-hidden flex flex-col">
          <CandidatesGrid
            onCandidateClick={(ticker, asof, strategy) =>
              setSelectedCandidate({ ticker, asof, strategy })
            }
          />
        </main>

        {/* Chatbot Sidebar */}
        <ChatSidebar />
      </div>

      {/* Candidate Detail Modal */}
      {selectedCandidate && (
        <CandidateDetailModal
          ticker={selectedCandidate.ticker}
          asof={selectedCandidate.asof}
          strategy={selectedCandidate.strategy}
          onClose={() => setSelectedCandidate(null)}
        />
      )}

      {/* Scan Modal (SSE streaming logs) */}
      <ScanModal />
    </div>
  );
}

export default App;
