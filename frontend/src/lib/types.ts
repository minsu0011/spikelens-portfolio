export type Session = "PREMARKET" | "RTH" | "AFTERHOURS";
export type Page<T> = { items: T[]; total: number; page: number; limit: number; pages: number };
export type User = { id: string; email: string; name: string; role: "USER" | "ADMIN" | "user" | "admin" };
export type MarketEvent = {
  id: string; ticker: string; event_time: string; session: Session; event_type: string;
  p0_price: number; t5_price: number; volume: number; price_path: number[];
  anomaly_score: number | null; data_quality_score: number | null; model_version: string | null;
  is_public: boolean; is_synthetic: boolean; created_at: string;
};
export type Summary = {
  total_events: number; tickers: number; total_volume: number; average_anomaly_score: number;
  by_session: { session: Session; count: number }[];
  daily_counts: { date: string; count: number }[];
  recent_events: MarketEvent[];
};
export type Upload = {
  id: string; original_filename: string; sha256: string; row_count: number;
  status: string; validation_errors: unknown[]; created_at: string;
};
export type Job = {
  id: string; upload_id: string; status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  progress: number; processed_rows: number; total_rows: number; attempts: number; max_attempts: number;
  error_code: string | null; error_message: string | null; retryable: boolean;
  created_at: string; started_at: string | null; completed_at: string | null;
};
export type AnalysisResult = {
  id: string; event_id: string; ticker: string; event_time: string; session: Session;
  anomaly_score: number; data_quality_score: number; event_summary: string; model_version: string;
  metrics: { fixture_only: boolean; validated_rows: number; missing_fields: number; path_points: number };
};
export type AdminMetrics = {
  users: number; total_jobs: number; jobs_by_status: { status: string; count: number }[];
  failure_rate: number; average_queue_wait_seconds: number | null; average_processing_seconds: number | null;
  cache: { hits: number; misses: number; hit_rate: number | null };
  api: { requests: number; p50_ms: number | null; p95_ms: number | null };
  dependencies: { database: string; redis: string };
};
