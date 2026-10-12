import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = { title: { default: "SpikeLens — Event Intelligence", template: "%s · SpikeLens" }, description: "합성 이벤트 데이터로 구축한 독립적인 이벤트 분석 포트폴리오. CSV 업로드, 비동기 분석, 실시간 작업 상태." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ko"><body><Providers><Shell>{children}</Shell></Providers></body></html>;
}
