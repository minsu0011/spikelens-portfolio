# 설계 결정

| 선택 | 이유와 한계 |
|---|---|
| FastAPI + 계층 분리 | Pydantic 입력 계약과 OpenAPI; Router/Service/Repository 역할 구분 |
| PostgreSQL 원장 | 관계형 소유권·UNIQUE·transaction·row lock과 migration |
| Redis/Celery + DB outbox | 비동기 처리와 cache; DB commit/게시 실패 구간을 복구하되 exactly-once delivery를 주장하지 않음 |
| SSE + polling | 단방향 상태 전송; 실제 DB 상태 기반 재접속 복구 |
| opaque session | DB 만료/로그아웃, HttpOnly와 CSRF, 운영 HTTPS 요구 |
| 별도 공개 snapshot | private history와 구현을 공개하지 않고 새 검증·commit부터 시작 |
| Public fixture provider | ML dependency 없이 실제 풀스택 경로를 유지; 예측 결과 제공하지 않음 |
