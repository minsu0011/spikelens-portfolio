"use client";

import { ArrowRight, LoaderCircle, ShieldCheck } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

export function AuthForm({ register = false }: { register?: boolean }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const client = useQueryClient();
  const router = useRouter();
  const mutation = useMutation({
    mutationFn: () => api<User>(register ? "/auth/register" : "/auth/login", { method: "POST", body: JSON.stringify({ email, password, ...(register ? { name } : {}) }) }),
    onSuccess: async (user) => { await client.cancelQueries(); client.removeQueries({ predicate: (query) => query.queryKey[0] !== "me" }); client.setQueryData(["me"], user); setPassword(""); router.push("/dashboard"); router.refresh(); },
  });
  return <div className="auth-page"><div className="auth-intro"><div className="eyebrow">YOUR PRIVATE WORKSPACE</div><h1>이벤트를 탐색하고,<br />분석을 연결하세요.</h1><p>공개 합성 이벤트를 둘러보고, 나만의 CSV 데이터를 올려 독립적인 데모 분석을 실행해 보세요.</p><div className="auth-note"><ShieldCheck size={20} /><p>업로드와 분석 작업은 사용자별로 분리됩니다. 비밀번호와 세션 토큰은 브라우저 저장소에 보관하지 않습니다.</p></div></div><section className="panel auth-card"><h2>{register ? "Create account" : "Welcome back"}</h2><p>{register ? "새로운 분석 워크스페이스를 만드세요." : "로그인하고 분석 작업을 이어가세요."}</p>{mutation.error && <div className="inline-error" role="alert">{mutation.error.message}</div>}<form className="form-stack" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>{register && <label>이름<input aria-label="Name" type="text" required minLength={2} maxLength={80} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} /></label>}<label>이메일<input aria-label="Email" type="email" required autoComplete="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} /></label><label>비밀번호<input aria-label="Password" type="password" required minLength={register ? 10 : 1} maxLength={128} autoComplete={register ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} />{register && <span className="form-note">10자 이상의 비밀번호를 사용하세요.</span>}</label><button className="button primary wide" type="submit" disabled={mutation.isPending}>{mutation.isPending ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}{register ? "계정 만들기" : "로그인"}</button></form><div className="auth-switch">{register ? "이미 계정이 있나요?" : "처음 방문하셨나요?"}<Link href={register ? "/login" : "/register"}>{register ? "로그인" : "회원가입"}</Link></div></section></div>;
}
