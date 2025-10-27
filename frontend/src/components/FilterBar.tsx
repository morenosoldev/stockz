import { Filter, SlidersHorizontal } from 'lucide-react';
import { useState } from 'react';
import type { CandidatesFilters } from '@/hooks/useCandidates';

export interface FilterBarProps {
  filters: CandidatesFilters;
  onFiltersChange: (filters: CandidatesFilters) => void;
}

export function FilterBar({ filters, onFiltersChange }: FilterBarProps) {
  const [showFilters, setShowFilters] = useState(false);

  const handleStrategyChange = (strategy: string) => {
    onFiltersChange({ ...filters, strategy: strategy || undefined, offset: 0 });
  };

  const handleMinScoreChange = (min_score: number) => {
    onFiltersChange({ ...filters, min_score, offset: 0 });
  };

  const handleSortChange = (sort_by: CandidatesFilters['sort_by']) => {
    onFiltersChange({ ...filters, sort_by, offset: 0 });
  };

  const handleSortOrderChange = (sort_order: 'asc' | 'desc') => {
    onFiltersChange({ ...filters, sort_order, offset: 0 });
  };

  const handleDateChange = (date: string) => {
    onFiltersChange({ ...filters, date: date || undefined, offset: 0 });
  };

  return (
    <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Filter className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            Filters
          </h3>
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
        >
          <SlidersHorizontal className="w-4 h-4" />
          <span>{showFilters ? 'Hide' : 'Show'} Filters</span>
        </button>
      </div>

      {/* Quick Filters (Always Visible) */}
      <div className="flex flex-wrap gap-3">
        {/* Strategy Filter */}
        <select
          value={filters.strategy || ''}
          onChange={(e) => handleStrategyChange(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">All Strategies</option>
          <option value="drop5">Drop 5%</option>
        </select>

        {/* Sort By */}
        <select
          value={filters.sort_by || 'score'}
          onChange={(e) =>
            handleSortChange(e.target.value as CandidatesFilters['sort_by'])
          }
          className="px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="score">Sort by Score</option>
          <option value="drop_pct">Sort by Drop %</option>
          <option value="volume_rvol">Sort by Volume</option>
          <option value="ticker">Sort by Ticker</option>
        </select>

        {/* Sort Order */}
        <select
          value={filters.sort_order || 'desc'}
          onChange={(e) => handleSortOrderChange(e.target.value as 'asc' | 'desc')}
          className="px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </div>

      {/* Advanced Filters (Collapsible) */}
      {showFilters && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-800 space-y-4">
          {/* Date Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Date
            </label>
            <input
              type="date"
              value={filters.date || ''}
              onChange={(e) => handleDateChange(e.target.value)}
              className="px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 w-full max-w-xs"
            />
          </div>

          {/* Min Score Slider */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Minimum Score: {((filters.min_score || 0) * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={filters.min_score || 0}
              onChange={(e) => handleMinScoreChange(parseFloat(e.target.value))}
              className="w-full max-w-md h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-primary-500"
            />
            <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-md">
              <span>0%</span>
              <span>50%</span>
              <span>100%</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
