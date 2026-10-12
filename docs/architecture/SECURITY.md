# 공개 데모 보안

Argon2id로 비밀번호를 hash하고 opaque 세션 토큰의 SHA256 digest만 DB에 저장한다. HttpOnly 세션 쿠키와 세션에 결합된 CSRF 토큰, Origin/SameSite 검사, 만료와 로그아웃 무효화를 적용한다. 관리자 role은 서버에서 확인하고 공개 회원가입으로 승격할 수 없다.

데이터 접근은 owner 조건을 SQL에 포함한다. 다른 사용자의 UUID를 알아도 업로드·작업·결과·SSE를 볼 수 없다. 공개 요약 캐시에는 사용자 데이터를 넣지 않는다. 로그인 제한은 계정 20회/15분과 peer 200회/15분으로 분리하며 PostgreSQL advisory lock으로 count race를 막는다. 변조 X-Forwarded-For를 앱에서 신뢰하지 않는다.

업로드는 HTTP body 10MiB·20,000행·UTF/schema·날짜·숫자·중복을 확인한다. 서버가 저장 키를 생성하고 Path Traversal을 거부한다. 임시 파일 write/fsync 후 원자적으로 게시하며 실패를 정리하고 기존 파일을 보존한다. 결과 CSV는 formula 문자열을 escape한다. 연결 문자열·비밀번호·쿠키·stack trace는 사용자 응답에 넣지 않는다.

새 공개 Git history, 명시적 allowlist, AST 의존성/파일 유형/개인 경로 검사와 독립 Gitleaks 검사를 사용한다. ORM tables는 허용하며 예측 dependency·모델 binary·실제 .env는 거부한다. 이미지도 별도 실제 화면·metadata 검토를 한다. 패턴 검사만으로 모든 유출 가능성을 보장하지 않는다.

현재는 loopback HTTP 개발 환경이다. 운영에는 HTTPS/Secure cookie, 최소 DB 권한·Redis ACL, 비밀값 관리, 이메일/비밀번호 복구, 저장소 보존·백업 복원·감사·경보와 quota 검증이 필요하다. 사용자 승인 없이 공개 push나 cloud 배포하지 않는다.
