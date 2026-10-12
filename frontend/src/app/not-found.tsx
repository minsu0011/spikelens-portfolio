import Link from "next/link";
export default function NotFound() { return <div className="state-panel"><h1>404</h1><h3>페이지를 찾을 수 없습니다</h3><p>주소를 확인하거나 이벤트 워크스페이스로 돌아가세요.</p><Link href="/dashboard" className="button primary">대시보드로 돌아가기</Link></div>; }
