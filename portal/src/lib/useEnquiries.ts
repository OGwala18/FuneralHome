import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchEnquiries, type EnquiryPage, type EnquiryQuery } from "./api";

/**
 * One place that talks to the enquiries endpoint, shared by Today, People,
 * Applications and Growth. Four copies of this logic is four places for a
 * race condition to hide.
 */
export function useEnquiries(query: EnquiryQuery) {
  const [page, setPage] = useState<EnquiryPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Serialised so an object literal at the call site does not refetch forever.
  const key = JSON.stringify(query);

  // Guards against a slow earlier request overwriting a newer result.
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const mine = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchEnquiries(JSON.parse(key) as EnquiryQuery);
      if (mine === requestId.current) setPage(result);
    } catch (err) {
      if (mine !== requestId.current) return;
      setError(
        err instanceof ApiError ? err.message : "Could not load enquiries.",
      );
    } finally {
      if (mine === requestId.current) setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    void load();
  }, [load]);

  return { page, rows: page?.rows ?? [], loading, error, reload: load };
}
