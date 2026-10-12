"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { UploadCloud } from "lucide-react";
import { api, queryString } from "@/lib/api";
import type { Job, Page } from "@/lib/types";
import { datetime, number, shortId } from "@/lib/format";
import { useAuth } from "@/components/providers";
import { AuthGate, Empty, ErrorState, Loading, PageTitle, Pagination, Status } from "@/components/ui";

export default function JobsPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ["jobs", status, page, user?.id], queryFn: () => api<Page<Job>>(`/jobs?${queryString({ status, page, limit: 15 })}`), enabled: !!user, refetchInterval: (query) => query.state.data?.items.some((job) => ["QUEUED", "RUNNING"].includes(job.status)) ? 3000 : false });
  return <><PageTitle eyebrow="FOLLOW THE WORK" title="Analysis jobs" description="실제 워커가 저장한 상태, 처리량과 결과를 확인하세요." action={<Link href="/upload" className="button primary"><UploadCloud size={15} />새 분석</Link>} /><AuthGate><div className="job-status-filter">{["", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED"].map((value) => <button key={value} className={status === value ? "active" : ""} onClick={() => { setStatus(value); setPage(1); }}>{value || "ALL JOBS"}</button>)}</div><section className="panel">{query.isPending ? <Loading /> : query.error ? <ErrorState error={query.error} retry={() => { void query.refetch(); }} /> : query.data && <>{query.data.items.length ? <div className="table-scroll"><table><thead><tr><th>JOB ID</th><th>STATUS</th><th>PROCESSED</th><th>PROGRESS</th><th>ATTEMPTS</th><th>CREATED · UTC</th><th /></tr></thead><tbody>{query.data.items.map((job) => <tr key={job.id}><td><Link className="job-link" href={`/jobs/${job.id}`}>{shortId(job.id)}</Link><span className="cell-sub">Upload {shortId(job.upload_id)}</span></td><td><Status value={job.status} /></td><td className="tabular">{number(job.processed_rows)} / {number(job.total_rows)}</td><td>{job.progress.toFixed(0)}%</td><td>{job.attempts} / {job.max_attempts}</td><td className="table-muted">{datetime(job.created_at)}</td><td><Link className="text-link" href={`/jobs/${job.id}`}>상세 보기</Link></td></tr>)}</tbody></table></div> : <Empty title="표시할 분석 작업이 없습니다" description="CSV를 업로드해 분석을 시작하거나 상태 필터를 변경하세요." />}<Pagination page={page} pages={query.data.pages} total={query.data.total} onPage={setPage} /></>}</section></AuthGate></>;
}
