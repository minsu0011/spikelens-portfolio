"use client";

import { Activity, ArrowRight, ArrowUpRight, Database, Layers3, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Summary } from "@/lib/types";
import { compactNumber, number, score } from "@/lib/format";
import { DailyChart, SessionChart } from "@/components/charts";
import { EventTable } from "@/components/event-table";
import { Empty, ErrorState, Loading, Metric, PageTitle } from "@/components/ui";

export default function DashboardPage() {
  const query = useQuery({ queryKey: ["summary"], queryFn: () => api<Summary>("/analytics/summary") });
  return <><PageTitle eyebrow="YOUR EVENT WORKSPACE" title="Overview" description="공개 합성 이벤트의 활동과 분포를 한눈에 확인하세요." action={<Link href="/upload" className="button primary"><UploadCloud size={16} />데이터 업로드</Link>} />{query.isPending ? <Loading /> : query.error ? <ErrorState error={query.error} retry={() => { void query.refetch(); }} /> : query.data && <><div className="metric-grid"><Metric label="TOTAL EVENTS" value={number(query.data.total_events)} note="공개 합성 이벤트" icon={<Activity size={16} />} /><Metric label="UNIQUE SYMBOLS" value={number(query.data.tickers)} note="가상 종목 코드" icon={<Layers3 size={16} />} /><Metric label="TRADE VOLUME" value={<span title={number(query.data.total_volume)}>{compactNumber(query.data.total_volume)}</span>} note="합성 거래 활동의 합계" icon={<Database size={16} />} /><Metric label="AVG. FIXTURE VALUE" value={score(query.data.average_anomaly_score)} note="사전 정의된 DEMO/FIXTURE · 0–100" icon={<Activity size={16} />} /></div><div className="dashboard-charts"><section className="panel"><div className="panel-heading"><div><h2>Event activity</h2><p>날짜별 합성 이벤트 분포</p></div><span className="subtle-tag">DAILY</span></div><DailyChart data={query.data.daily_counts} /></section><section className="panel"><div className="panel-heading"><div><h2>By session</h2><p>거래 세션별 이벤트 수</p></div></div><SessionChart data={query.data.by_session} /><div className="chart-note">합성 데이터의 구성 비율이며 실제 시장 분포를 나타내지 않습니다.</div></section></div><section className="panel"><div className="panel-heading"><div><h2>Recent events</h2><p>최근 등록된 공개 합성 이벤트</p></div><Link href="/events" className="text-link">전체 보기<ArrowUpRight size={16} /></Link></div>{query.data.recent_events.length ? <EventTable events={query.data.recent_events} /> : <Empty />}</section><div className="callout"><div><strong>직접 데이터를 분석해 보세요.</strong><p>CSV를 올리고 서버에서 처리되는 분석 작업의 상태와 결과를 확인하세요.</p></div><Link href="/upload" className="button secondary">분석 시작<ArrowRight size={16} /></Link></div></>}</>;
}
