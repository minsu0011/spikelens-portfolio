"use client";
import { ErrorState } from "@/components/ui";
export default function ErrorPage({ reset }: { error: Error; reset: () => void }) { return <ErrorState error={new Error("화면을 표시하지 못했습니다. 다시 불러오거나 잠시 후 시도하세요.")} retry={reset} />; }
