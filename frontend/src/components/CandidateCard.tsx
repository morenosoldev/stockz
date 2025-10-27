import { TrendingDown, Activity, Calendar } from 'lucide-react';
import { formatRelativeTime, getScoreColor } from '@/hooks/useCandidates';

export interface CandidateCardProps {
  ticker: string;
  asof: string;
  strategy: string;
  score: number;
  price?: number | null;
  drop_pct?: number | null;
  volume_rvol?: number | null;
  onClick?: () => void;
}

export function CandidateCard({
  ticker,
  asof,
  strategy,
  score,
  price,
  drop_pct,
  volume_rvol,
  onClick,
}: CandidateCardProps) {
  const scoreColors = getScoreColor(score);
  const relativeTime = formatRelativeTime(asof);

  return (
    <div
      onClick={onClick}
      className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4 hover:shadow-lg hover:-translate-y-1 transition-all duration-200 cursor-pointer group"
    >
      {/* Header: Ticker and Score */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-2xl font-bold text-gray-900 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
            {ticker}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              {strategy}
            </span>
          </div>
        </div>
        <div
          className={`px-3 py-1.5 rounded-full border ${scoreColors.bg} ${scoreColors.text} ${scoreColors.border}`}
        >
          <span className="text-sm font-semibold">
            {(score * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="space-y-2">
        {drop_pct !== null && drop_pct !== undefined && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <TrendingDown className="w-4 h-4" />
              <span>Drop</span>
            </div>
            <span className="text-sm font-semibold text-error-600 dark:text-error-400">
              {drop_pct.toFixed(2)}%
            </span>
          </div>
        )}

        {price !== null && price !== undefined && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <span>$</span>
              <span>Price</span>
            </div>
            <span className="text-sm font-semibold text-gray-900 dark:text-white">
              ${price.toFixed(2)}
            </span>
          </div>
        )}

        {volume_rvol !== null && volume_rvol !== undefined && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <Activity className="w-4 h-4" />
              <span>Volume</span>
            </div>
            <span className="text-sm font-semibold text-gray-900 dark:text-white">
              {volume_rvol.toFixed(2)}x
            </span>
          </div>
        )}
      </div>

      {/* Footer: Date */}
      <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-800">
        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <Calendar className="w-3.5 h-3.5" />
          <span>{relativeTime}</span>
        </div>
      </div>
    </div>
  );
}
