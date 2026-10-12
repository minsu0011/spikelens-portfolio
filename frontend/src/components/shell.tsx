"use client";

import { Activity, ArrowUpRight, BarChart3, ChevronRight, Files, LayoutDashboard, LogOut, Menu, ShieldCheck, UploadCloud, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "./providers";

const links = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/events", label: "Event explorer", icon: Activity },
  { href: "/upload", label: "Upload & analyze", icon: UploadCloud },
  { href: "/jobs", label: "Analysis jobs", icon: Files },
];
export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const client = useQueryClient();
  const { user, loading } = useAuth();
  const [open, setOpen] = useState(false);
  const logout = useMutation({ mutationFn: () => api<void>("/auth/logout", { method: "POST" }), onSuccess: async () => { await client.cancelQueries(); client.setQueryData(["me"], null); client.removeQueries({ predicate: (query) => query.queryKey[0] !== "me" }); router.push("/"); router.refresh(); } });
  const landing = pathname === "/";
  const auth = pathname === "/login" || pathname === "/register";
  const admin = user?.role.toUpperCase() === "ADMIN";
  return <div className={`app ${landing || auth ? "full-width" : ""}`}>
    <a className="skip-link" href="#main-content">본문으로 이동</a>
    <header className="topbar"><Link href="/" className="brand" aria-label="SpikeLens home"><span className="brand-mark"><BarChart3 size={21} /></span>Spike<span>Lens</span><span className="brand-tag">EVENT INTELLIGENCE</span></Link><div className="topbar-right"><span className="demo-badge"><span />SYNTHETIC DEMO</span>{user ? <><span className="user-name">{user.name || user.email}</span><button aria-label="Log out" title="로그아웃" className="icon-button" onClick={() => logout.mutate()} disabled={logout.isPending}><LogOut size={17} /></button></> : !loading && <Link href="/login" className="top-login">로그인<ArrowUpRight size={15} /></Link>}<button className="icon-button menu-toggle" aria-label={open ? "메뉴 닫기" : "메뉴 열기"} aria-expanded={open} onClick={() => setOpen(!open)}>{open ? <X size={20} /> : <Menu size={20} />}</button></div></header>
    {!landing && !auth && <><button aria-label="메뉴 닫기" className={`sidebar-shade ${open ? "visible" : ""}`} onClick={() => setOpen(false)} /><aside className={`sidebar ${open ? "open" : ""}`}><div className="nav-label">WORKSPACE</div><nav>{links.map(({ href, label, icon: Icon }) => <Link onClick={() => setOpen(false)} className={`nav-link ${pathname.startsWith(href) ? "active" : ""}`} href={href} key={href}><Icon size={18} />{label}{pathname.startsWith(href) && <ChevronRight className="nav-arrow" size={14} />}</Link>)}{admin && <Link onClick={() => setOpen(false)} className={`nav-link ${pathname.startsWith("/admin") ? "active" : ""}`} href="/admin"><ShieldCheck size={18} />Operations</Link>}</nav><div className="sidebar-bottom"><div className="side-note"><span className="dot" />Independent demo environment</div><p>PUBLIC DEMO: 합성 fixture와 데이터 품질 검사만 제공합니다. 비공개 예측 구현은 포함하지 않습니다.</p><Link href="/" className="side-about">About SpikeLens<ArrowUpRight size={13} /></Link></div></aside></>}
    <main id="main-content" className="main-content">{logout.error && <div className="inline-error" role="alert">{logout.error.message}</div>}{children}</main>
    <footer className="footer"><span>SpikeLens · Backend portfolio project</span><span>합성 데모 데이터 · 투자 추천 아님</span></footer>
  </div>;
}
