import { useState } from 'react';
import { Loader2, AlertCircle, TrendingUp } from 'lucide-react';
import { useCandidates, type CandidatesFilters } from '@/hooks/useCandidates';
import { CandidateCard } from './CandidateCard';
import { FilterBar } from './FilterBar';

export interface CandidatesGridProps {
  onCandidateClick?: (ticker: string, asof: string, strategy: string) => void;
}

export function CandidatesGrid({ onCandidateClick }: CandidatesGridProps) {
  const [filters, setFilters] = useState<CandidatesFilters>({
    limit: 50,
    offset: 0,
    sort_by: 'score',
    sort_order: 'desc',
  });

  const { data, isLoading, error } = useCandidates(filters);

  // Loading State
  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 text-primary-500 animate-spin mx-auto mb-4" />
          <p className="text-gray-600 dark:text-gray-400">Loading candidates...</p>
        </div>
      </div>
    );
  }

  // Error State
  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md">
          <AlertCircle className="w-12 h-12 text-error-500 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
            Failed to Load Candidates
          </h3>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            {error instanceof Error ? error.message : 'An unknown error occurred'}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
          >
            Reload Page
          </button>
        </div>
      </div>
    );
  }

  // Empty State
  if (!data || data.candidates.length === 0) {
    return (
      <div className="flex-1 flex flex-col">
        <FilterBar filters={filters} onFiltersChange={setFilters} />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <TrendingUp className="w-16 h-16 text-gray-300 dark:text-gray-700 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              No Candidates Found
            </h3>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Try scanning the market or adjusting your filters to find recovery candidates.
            </p>
            <button
              onClick={() =>
                setFilters({ limit: 50, offset: 0, sort_by: 'score', sort_order: 'desc' })
              }
              className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
            >
              Reset Filters
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Success State with Data
  return (
    <div className="flex-1 flex flex-col">
      {/* Filter Bar */}
      <FilterBar filters={filters} onFiltersChange={setFilters} />

      {/* Results Summary */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Showing <span className="font-semibold text-gray-900 dark:text-white">{data.candidates.length}</span> of{' '}
          <span className="font-semibold text-gray-900 dark:text-white">{data.total}</span> candidates
        </p>
      </div>

      {/* Candidates Grid */}
      <div className="flex-1 overflow-auto p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {data.candidates.map((candidate) => (
            <CandidateCard
              key={`${candidate.ticker}-${candidate.asof}-${candidate.strategy}`}
              ticker={candidate.ticker}
              asof={candidate.asof}
              strategy={candidate.strategy}
              score={candidate.score}
              price={candidate.price}
              drop_pct={candidate.drop_pct}
              volume_rvol={candidate.volume_rvol}
              onClick={() =>
                onCandidateClick?.(candidate.ticker, candidate.asof, candidate.strategy)
              }
            />
          ))}
        </div>

        {/* Pagination (if needed) */}
        {data.total > (filters.limit || 50) && (
          <div className="mt-6 flex items-center justify-center gap-4">
            <button
              onClick={() =>
                setFilters({
                  ...filters,
                  offset: Math.max(0, (filters.offset || 0) - (filters.limit || 50)),
                })
              }
              disabled={(filters.offset || 0) === 0}
              className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            <span className="text-sm text-gray-600 dark:text-gray-400">
              Page {Math.floor((filters.offset || 0) / (filters.limit || 50)) + 1} of{' '}
              {Math.ceil(data.total / (filters.limit || 50))}
            </span>
            <button
              onClick={() =>
                setFilters({
                  ...filters,
                  offset: (filters.offset || 0) + (filters.limit || 50),
                })
              }
              disabled={(filters.offset || 0) + (filters.limit || 50) >= data.total}
              className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
