"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Job } from "@/lib/types";

export function useJobStream(id: string, enabled: boolean) {
  const client = useQueryClient();
  const [connection, setConnection] = useState<"connecting" | "connected" | "reconnecting">("connecting");
  useEffect(() => {
    if (!enabled) return;
    const source = new EventSource(`/api/v1/jobs/${id}/stream`);
    source.onopen = () => setConnection("connected");
    source.onerror = () => setConnection("reconnecting");
    const update = (event: MessageEvent<string>) => {
      try {
        const job = JSON.parse(event.data) as Job;
        if (job.id !== id || typeof job.progress !== "number") return;
        client.setQueryData(["job", id], job);
        if (["SUCCEEDED", "FAILED"].includes(job.status)) { source.close(); void client.invalidateQueries({ queryKey: ["jobs"] }); void client.invalidateQueries({ queryKey: ["job-results", id] }); }
      } catch { void client.invalidateQueries({ queryKey: ["job", id] }); }
    };
    for (const name of ["job.started", "job.progress", "job.completed", "job.failed", "job.queued", "job.snapshot"]) source.addEventListener(name, update as EventListener);
    source.onmessage = update;
    return () => source.close();
  }, [id, enabled, client]);
  return connection;
}
