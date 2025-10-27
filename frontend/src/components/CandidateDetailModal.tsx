import { useEffect, useState } from 'react';
import { X, Loader2, ExternalLink, TrendingDown, Activity, Calendar, Info } from 'lucide-react';
import { useCandidateDetail } from '@/hooks/useCandidates';
import { getScoreColor } from '@/hooks/useCandidates';

export interface CandidateDetailModalProps {
  ticker: string | null;
  asof: string | null;
  strategy?: string;
  onClose: () => void;
}

type TabType = 'overview' | 'reasoning' | 'attribution';

export function CandidateDetailModal({
  ticker,
  asof,
  strategy,
  onClose,
}: CandidateDetailModalProps) {
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const { data, isLoading, error } = useCandidateDetail(ticker, asof, strategy);

  // Handle ESC key to close modal
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  // Don't render if no ticker/asof
  if (!ticker || !asof) {
    return null;
  }

  const scoreColors = data ? getScoreColor(data.score) : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-900 rounded-lg shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-gray-200 dark:border-gray-800 p-6">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-4">
                <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
                  {ticker}
                </h2>
                {data && scoreColors && (
                  <div
                    className={`px-3 py-1.5 rounded-full border ${scoreColors.bg} ${scoreColors.text} ${scoreColors.border}`}
                  >
                    <span className="text-sm font-semibold">
                      {(data.score * 100).toFixed(0)}% Score
                    </span>
                  </div>
                )}
              </div>
              {data && (
                <div className="mt-2 flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                  {data.name && <span>{data.name}</span>}
                  {data.sector && (
                    <>
                      <span>•</span>
                      <span>{data.sector}</span>
                    </>
                  )}
                  <span>•</span>
                  <span className="uppercase">{data.strategy}</span>
                </div>
              )}
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            >
              <X className="w-6 h-6" />
            </button>
          </div>

          {/* Tabs */}
          <div className="mt-6 flex gap-1 border-b border-gray-200 dark:border-gray-800">
            {(['overview', 'reasoning', 'attribution'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
                  activeTab === tab
                    ? 'border-b-2 border-primary-500 text-primary-600 dark:text-primary-400'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
            </div>
          )}

          {error && (
            <div className="text-center py-12">
              <p className="text-error-600 dark:text-error-400">
                Failed to load candidate details
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                {error instanceof Error ? error.message : 'Unknown error'}
              </p>
            </div>
          )}

          {data && (
            <>
              {/* Overview Tab */}
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  {/* Key Metrics Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <MetricCard
                      label="Score"
                      value={`${(data.score * 100).toFixed(0)}%`}
                      icon={<Activity className="w-5 h-5" />}
                    />
                    {data.drop_pct !== null && data.drop_pct !== undefined && (
                      <MetricCard
                        label="Drop"
                        value={`${data.drop_pct.toFixed(2)}%`}
                        icon={<TrendingDown className="w-5 h-5" />}
                        valueClassName="text-error-600 dark:text-error-400"
                      />
                    )}
                    {data.price !== null && data.price !== undefined && (
                      <MetricCard
                        label="Price"
                        value={`$${data.price.toFixed(2)}`}
                        icon={<span className="text-lg">$</span>}
                      />
                    )}
                    {data.volume_rvol !== null && data.volume_rvol !== undefined && (
                      <MetricCard
                        label="Volume Ratio"
                        value={`${data.volume_rvol.toFixed(2)}x`}
                        icon={<Activity className="w-5 h-5" />}
                      />
                    )}
                  </div>

                  {/* Date Info */}
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                    <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                      <Calendar className="w-4 h-4" />
                      <span>Identified on {new Date(data.asof).toLocaleDateString()}</span>
                      <span>•</span>
                      <span>Run Status: {data.run_status}</span>
                    </div>
                  </div>

                  {/* Quick Actions */}
                  <div className="flex gap-3">
                    <a
                      href={`https://finance.yahoo.com/quote/${ticker}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
                    >
                      <ExternalLink className="w-4 h-4" />
                      <span>View on Yahoo Finance</span>
                    </a>
                  </div>
                </div>
              )}

              {/* Reasoning Tab */}
              {activeTab === 'reasoning' && (
                <div className="space-y-4">
                  <div className="flex items-start gap-3 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                    <Info className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-1">
                        Strategy Reasoning
                      </h4>
                      <p className="text-sm text-blue-800 dark:text-blue-300">
                        This section shows why the strategy identified this candidate as having recovery potential.
                      </p>
                    </div>
                  </div>

                  {/* Display rationale JSON in readable format */}
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">
                      Rationale Details
                    </h4>
                    <pre className="text-xs text-gray-700 dark:text-gray-300 overflow-auto">
                      {JSON.stringify(data.rationale, null, 2)}
                    </pre>
                  </div>
                </div>
              )}

              {/* Attribution Tab */}
              {activeTab === 'attribution' && (
                <div className="space-y-4">
                  <div className="flex items-start gap-3 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                    <Info className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-sm font-semibold text-green-900 dark:text-green-100 mb-1">
                        Data Attribution
                      </h4>
                      <p className="text-sm text-green-800 dark:text-green-300">
                        All data sources are tracked for transparency and reproducibility.
                      </p>
                    </div>
                  </div>

                  {/* Display attribution JSON */}
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">
                      Source Information
                    </h4>
                    <pre className="text-xs text-gray-700 dark:text-gray-300 overflow-auto">
                      {JSON.stringify(data.attribution, null, 2)}
                    </pre>
                  </div>

                  {/* Run Metadata */}
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">
                      Run Metadata
                    </h4>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-gray-400">Run ID:</span>
                        <span className="text-gray-900 dark:text-white font-mono text-xs">
                          {data.run_id}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-gray-400">Status:</span>
                        <span className="text-gray-900 dark:text-white">{data.run_status}</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// Helper component for metric cards
interface MetricCardProps {
  label: string;
  value: string;
  icon?: React.ReactNode;
  valueClassName?: string;
}

function MetricCard({ label, value, icon, valueClassName }: MetricCardProps) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400 mb-2">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <div className={`text-2xl font-bold ${valueClassName || 'text-gray-900 dark:text-white'}`}>
        {value}
      </div>
    </div>
  );
}
