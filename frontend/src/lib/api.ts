import createClient from 'openapi-fetch';
import type { paths } from './api-types';

/**
 * Type-safe API client for Recover-Bot backend.
 * Automatically generated from OpenAPI schema.
 *
 * Usage:
 * ```typescript
 * const { data, error } = await apiClient.GET('/v1/candidates', {
 *   params: { query: { date: '2025-10-25' } }
 * });
 * ```
 */
export const apiClient = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

/**
 * Helper to check if a response has an error.
 */
export function isApiError<T>(response: { data?: T; error?: unknown }): response is { error: unknown } {
  return !!response.error;
}
