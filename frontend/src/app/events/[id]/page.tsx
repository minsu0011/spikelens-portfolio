"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Clock, Database, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { MarketEvent } from "@/lib/types";
import { datetime, number, price, score, sessionName } from "@/lib/format";
import { PriceChart } from "@/components/charts";
import { ErrorState, Loading, Metric } from "@/components/ui";

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const query = useQuery({ queryKey: ["event", id], queryFn: () => api<MarketEvent>(`/events/${id}`) });
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorState error={query.error} retry={() => { void query.refetch(); }} />;
  const event = query.data;
  if (!event) return null;
  const change = ((event.t5_price - event.p0_price) / event.p0_price) * 100;
  return <><Link href="/events" className="back-link"><ArrowLeft size={15} />Event explorer</Link><div className="event-detail-title"><div><div className="eyebrow">EVENT DETAIL / {event.event_type}</div><h1>{event.ticker}<span className={`session-badge session-${event.session.toLowerCase()}`}>{sessionName(event.session)}</span></h1><p><Clock size={14} />{datetime(event.event_time)}</p></div><span className="subtle-tag">{event.is_synthetic ? "SYNTHETIC EVENT" : "USER UPLOAD"}</span></div><div className="metric-grid"><Metric label="REFERENCE PRICE · P0" value={price(event.p0_price)} note="이벤트 기준 가격" /><Metric label="REFERENCE PRICE · T5" value={price(event.t5_price)} note="관측 기준 가격" /><Metric label="PRICE CHANGE" value={<span className={change >= 0 ? "positive" : "negative"}>{change >= 0 ? "+" : ""}{change.toFixed(2)}%</span>} note="P0에서 T5까지의 변화" /><Metric label="TRADE VOLUME" value={number(event.volume)} note="제공된 거래 활동량" icon={<Database size={16} />} /></div><div className="event-detail-grid"><section className="panel"><div className="panel-heading"><div><h2>Observed price path</h2><p>{event.price_path.length}개의 가격 관측값 · USD</p></div><span className="subtle-tag">{event.is_synthetic ? "DEMO PATH" : "UPLOADED PATH"}</span></div><PriceChart prices={event.price_path} /><div className="chart-note">가격 경로는 제공된 값의 순서입니다. 관측값 사이의 실제 시각 정보는 포함하지 않습니다.</div></section><section className="panel score-panel"><div className="panel-heading"><div><h2>Demo analysis</h2><p>PUBLIC DEMO · FIXTURE ONLY</p></div><ShieldCheck size={19} /></div><div className="big-score">{score(event.anomaly_score)}<span>/ 100</span></div><div className="score-caption">DEMO/FIXTURE display value</div><div className="quality-row"><span>Data quality</span><strong>{score(event.data_quality_score)} / 100</strong></div><div className="quality-row"><span>Provider version</span><code>{event.model_version ?? "아직 분석되지 않음"}</code></div><p className="analysis-note">표시 값은 사전 정의된 합성 fixture입니다. 입력 가격이나 거래량으로 예측 점수를 계산하지 않습니다. 비공개 분석 구현은 포함되지 않습니다.</p></section></div><section className="panel metadata-panel"><div className="panel-heading"><h2>Event metadata</h2></div><dl><div><dt>Event ID</dt><dd className="mono">{event.id}</dd></div><div><dt>등록 시각</dt><dd>{datetime(event.created_at)}</dd></div><div><dt>데이터 출처</dt><dd>{event.is_synthetic ? "Synthetic generator · independent demo" : "사용자 CSV 업로드"}</dd></div><div><dt>공개 범위</dt><dd>{event.is_public ? "공개 합성 데모" : "소유자 전용"}</dd></div></dl></section></>;
}
