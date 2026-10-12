"use client";

import { Filter, Search, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, queryString } from "@/lib/api";
import type { MarketEvent, Page } from "@/lib/types";
import { EventTable } from "@/components/event-table";
import { Empty, ErrorState, Loading, PageTitle, Pagination } from "@/components/ui";

const initial = { ticker: "", session: "", event_date_from: "", event_date_to: "", event_type: "", sort: "event_time_desc" };
export default function EventsPage() {
  const [draft, setDraft] = useState(initial);
  const [filters, setFilters] = useState(initial);
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ["events", filters, page], queryFn: () => api<Page<MarketEvent>>(`/events?${queryString({ ...filters, page, limit: 15 })}`) });
  const field = (name: keyof typeof initial, value: string) => setDraft((old) => ({ ...old, [name]: value }));
  return <><PageTitle eyebrow="DISCOVER THE DETAILS" title="Event explorer" description="종목과 세션으로 공개 합성 이벤트 또는 내 비공개 이벤트를 탐색하세요." action={<span className="subtle-tag"><Filter size={14} />SERVER-SIDE FILTERS</span>} /><form className="filters panel" onSubmit={(event) => { event.preventDefault(); setPage(1); setFilters(draft); }}><div className="filter-top"><div className="search-input"><Search size={17} /><input aria-label="Ticker" placeholder="종목 코드 검색 · 예: DEM001" value={draft.ticker} onChange={(e) => field("ticker", e.target.value.toUpperCase())} maxLength={16} /></div><label><span className="sr-only">Session</span><select aria-label="Session" value={draft.session} onChange={(e) => field("session", e.target.value)}><option value="">모든 세션</option><option value="PREMARKET">Pre-market</option><option value="RTH">Regular hours</option><option value="AFTERHOURS">After-hours</option></select></label><label><span className="sr-only">Sort</span><select aria-label="Sort" value={draft.sort} onChange={(e) => field("sort", e.target.value)}><option value="event_time_desc">최신순</option><option value="event_time_asc">오래된순</option><option value="anomaly_desc">Fixture 표시 값 높은순</option></select></label><button type="submit" className="button primary"><SlidersHorizontal size={15} />필터 적용</button></div><div className="filter-bottom"><label>시작 날짜<input aria-label="From date" type="date" value={draft.event_date_from} onChange={(e) => field("event_date_from", e.target.value)} /></label><label>종료 날짜<input aria-label="To date" type="date" value={draft.event_date_to} onChange={(e) => field("event_date_to", e.target.value)} /></label><label>이벤트 유형<select aria-label="Event type" value={draft.event_type} onChange={(e) => field("event_type", e.target.value)}><option value="">전체 유형</option><option value="PRICE_SPIKE">Price spike</option><option value="VOLUME_SURGE">Volume surge</option><option value="VOLATILITY">Volatility</option></select></label><button type="button" className="text-link reset-filter" onClick={() => { setDraft(initial); setFilters(initial); setPage(1); }}>필터 초기화</button></div></form><section className="panel events-panel">{query.isPending ? <Loading /> : query.error ? <ErrorState error={query.error} retry={() => { void query.refetch(); }} /> : query.data && <>{query.data.items.length ? <EventTable events={query.data.items} /> : <Empty title="조건에 맞는 이벤트가 없습니다" description="종목 코드나 날짜, 세션 필터를 변경해 보세요." />}<Pagination page={page} pages={query.data.pages} total={query.data.total} onPage={setPage} /></>}</section><p className="footnote">공개 이벤트는 합성 데모입니다. 사용자 업로드 이벤트는 소유자에게만 표시됩니다.</p></>;
}
