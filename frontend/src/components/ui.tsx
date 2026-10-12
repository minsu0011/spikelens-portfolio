"use client";

import { AlertCircle, ArrowRight, Database, LoaderCircle, RefreshCw } from "lucide-react";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { useAuth } from "./providers";

export function PageTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return <div className="page-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>;
}
export function Loading({ label = "데이터를 불러오는 중입니다…" }: { label?: string }) {
  return <div className="state-panel" role="status"><LoaderCircle className="spin" size={22} /><p>{label}</p></div>;
}
export function ErrorState({ error, retry }: { error: Error; retry?: () => void }) {
  return <div className="state-panel error-panel" role="alert"><AlertCircle size={24} /><h3>요청을 완료하지 못했습니다</h3><p>{error.message}</p>{error instanceof ApiError && error.requestId && <small>Request ID · {error.requestId}</small>}{retry && <button className="button secondary" onClick={retry}><RefreshCw size={15} />다시 시도</button>}</div>;
}
export function Empty({ title = "아직 데이터가 없습니다", description = "조건을 바꾸거나 새 데이터를 업로드해 보세요.", action }: { title?: string; description?: string; action?: React.ReactNode }) {
  return <div className="state-panel"><Database size={25} /><h3>{title}</h3><p>{description}</p>{action}</div>;
}
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading, error, refresh } = useAuth();
  if (loading) return <Loading label="로그인 상태를 확인하는 중입니다…" />;
  if (error) return <ErrorState error={error} retry={refresh} />;
  if (!user) return <Empty title="나만의 분석 워크스페이스" description="로그인하면 파일을 업로드하고 분석 작업과 결과를 관리할 수 있습니다." action={<Link href="/login" className="button primary">로그인<ArrowRight size={16} /></Link>} />;
  return <>{children}</>;
}
export function Metric({ label, value, note, icon }: { label: string; value: React.ReactNode; note: string; icon?: React.ReactNode }) {
  return <div className="metric-card"><div className="metric-label">{label}{icon}</div><div className="metric-value">{value}</div><div className="metric-note">{note}</div></div>;
}
export function Status({ value }: { value: string }) { return <span className={`status status-${value.toLowerCase()}`}><span />{value}</span>; }
export function Pagination({ page, pages, total, onPage }: { page: number; pages: number; total: number; onPage: (page: number) => void }) {
  return <div className="pagination"><span>{total.toLocaleString()}개 결과 · {page} / {Math.max(pages, 1)} 페이지</span><div><button className="button small secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>이전</button><button className="button small secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>다음</button></div></div>;
}
