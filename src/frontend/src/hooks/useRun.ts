"use client";
import { useCallback, useEffect, useState } from "react";
import type { Run, TraceEvent } from "@/types/contracts";
import { getRun, getEvents } from "@/services/runs";

export function useRun(runId: string, pollMs = 3000) {
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [r, e] = await Promise.all([getRun(runId), getEvents(runId)]);
      setRun(r);
      setEvents(e);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    reload();
    const id = setInterval(reload, pollMs);
    return () => clearInterval(id);
  }, [reload, pollMs]);

  return { run, events, loading, error, reload };
}