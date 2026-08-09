import { useCallback, useEffect, useState } from 'react';
import { requestJson } from '../services/http';

export interface JsonQueryState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  retry: () => void;
}

export function useJsonQuery<T>(url: string | null): JsonQueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(Boolean(url));
  const [error, setError] = useState<Error | null>(null);
  const [revision, setRevision] = useState(0);
  const retry = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    if (!url) { setLoading(false); setError(null); return; }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void requestJson<T>(url, { signal: controller.signal })
      .then((value) => setData(value))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason : new Error('Request failed'));
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision, url]);

  return { data, loading, error, retry };
}
