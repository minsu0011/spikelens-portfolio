"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { datetime, number, price, score, sessionName } from "@/lib/format";
import type { MarketEvent } from "@/lib/types";

export function EventTable({ events }: { events: MarketEvent[] }) {
  return <div className="table-scroll"><table><thead><tr><th>SYMBOL / EVENT</th><th>EVENT TIME · UTC</th><th>SESSION</th><th>PRICE CHANGE</th><th>VOLUME</th><th>DEMO/FIXTURE</th><th><span className="sr-only">상세</span></th></tr></thead><tbody>{events.map((event) => {
    const change = ((event.t5_price - event.p0_price) / event.p0_price) * 100;
    return <tr key={event.id}><td><Link className="symbol-link" href={`/events/${event.id}`}>{event.ticker}</Link><span className="cell-sub">{event.event_type}</span></td><td className="table-muted">{datetime(event.event_time)}</td><td><span className={`session-badge session-${event.session.toLowerCase()}`}>{sessionName(event.session)}</span></td><td><span className={change >= 0 ? "positive" : "negative"}>{change >= 0 ? "+" : ""}{change.toFixed(2)}%</span><span className="cell-sub">{price(event.t5_price)}</span></td><td className="tabular">{number(event.volume)}</td><td><div className="score-cell"><span>{score(event.anomaly_score)}</span>{event.anomaly_score != null && <span className="score-track"><span style={{ width: `${Math.min(100, Math.max(0, event.anomaly_score))}%` }} /></span>}</div></td><td><Link className="table-arrow" href={`/events/${event.id}`} aria-label={`${event.ticker} 이벤트 상세`}><ArrowUpRight size={16} /></Link></td></tr>;
  })}</tbody></table></div>;
}
