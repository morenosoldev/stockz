import { useQuery, type UseQueryOptions } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import type { paths } from '@/lib/api-types';

// Type definitions from OpenAPI schema
type CandidatesResponse =
  paths['/v1/candidates']['get']['responses']['200']['content']['application/json'];
type CandidateDetailResponse =
  paths['/v1/candidate/{ticker}/{asof}']['get']['responses']['200']['content']['application/json'];

export interface CandidatesFilters {
  date?: string; // YYYY-MM-DD
  strategy?: string;
  min_score?: number;
  limit?: number;
  offset?: number;
  sort_by?: 'score' | 'drop_pct' | 'ticker' | 'volume_rvol';
  sort_order?: 'asc' | 'desc';
}

/**
 * Hook to fetch list of candidates with filtering and pagination
 */
export function useCandidates(
  filters: CandidatesFilters = {},
  options?: Omit<UseQueryOptions<CandidatesResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery<CandidatesResponse>({
    queryKey: ['candidates', filters],
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/v1/candidates', {
        params: {
          query: {
            date: filters.date,
            strategy: filters.strategy,
            min_score: filters.min_score,
            limit: filters.limit || 50,
            offset: filters.offset || 0,
            sort_by: filters.sort_by || 'score',
            sort_order: filters.sort_order || 'desc',
          },
        },
      });

      if (error) {
        throw new Error(`Failed to fetch candidates: ${error}`);
      }

      return data;
    },
    // Auto-refetch every 10 seconds if there are candidates
    refetchInterval: 10000,
    staleTime: 5000,
    ...options,
  });
}

/**
 * Hook to fetch detailed information for a specific candidate
 */
export function useCandidateDetail(
  ticker: string | null,
  asof: string | null, // YYYY-MM-DD
  strategy?: string,
  options?: Omit<UseQueryOptions<CandidateDetailResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery<CandidateDetailResponse>({
    queryKey: ['candidate-detail', ticker, asof, strategy],
    queryFn: async () => {
      if (!ticker || !asof) {
        throw new Error('Ticker and date are required');
      }

      const { data, error } = await apiClient.GET('/v1/candidate/{ticker}/{asof}', {
        params: {
          path: { ticker, asof },
          query: strategy ? { strategy } : undefined,
        },
      });

      if (error) {
        throw new Error(`Failed to fetch candidate detail: ${error}`);
      }

      return data;
    },
    enabled: !!ticker && !!asof, // Only run query if ticker and asof are provided
    staleTime: 30000, // Detail data is less volatile
    ...options,
  });
}

/**
 * Helper to format relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 7) {
    return date.toLocaleDateString();
  } else if (diffDays > 0) {
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  } else if (diffHours > 0) {
    return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  } else if (diffMinutes > 0) {
    return `${diffMinutes} minute${diffMinutes > 1 ? 's' : ''} ago`;
  } else {
    return 'Just now';
  }
}

/**
 * Helper to get score color class based on score value
 */
export function getScoreColor(score: number): {
  bg: string;
  text: string;
  border: string;
} {
  if (score >= 0.8) {
    return {
      bg: 'bg-success-100 dark:bg-success-900/20',
      text: 'text-success-700 dark:text-success-400',
      border: 'border-success-300 dark:border-success-700',
    };
  } else if (score >= 0.6) {
    return {
      bg: 'bg-warning-100 dark:bg-warning-900/20',
      text: 'text-warning-700 dark:text-warning-400',
      border: 'border-warning-300 dark:border-warning-700',
    };
  } else {
    return {
      bg: 'bg-gray-100 dark:bg-gray-800',
      text: 'text-gray-700 dark:text-gray-400',
      border: 'border-gray-300 dark:border-gray-700',
    };
  }
}
