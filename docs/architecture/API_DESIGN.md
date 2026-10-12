# REST API

OpenAPI schema와 Swagger `/docs`를 제공한다. 실제 서비스는 `http://localhost:8200/docs`다. 전체 23개 HTTP operation을 유지한다.

| 경로 | 메서드 | 역할 |
|---|---|---|
| `/api/v1/health/live`, `/ready` | GET | 프로세스 생존 / DB·Redis 준비 |
| `/api/v1/auth/register`, `/login`, `/logout` | POST | 인증 및 세션 무효화 |
| `/api/v1/auth/me` | GET | 현재 사용자 |
| `/api/v1/events` | GET, POST | 필터·페이지네이션 / 비공개 이벤트 생성 |
| `/api/v1/events/{id}` | GET, PUT, DELETE | 권한 있는 조회·갱신·삭제 |
| `/api/v1/analytics/summary` | GET | 공개 합성 데이터 요약 |
| `/api/v1/uploads` | GET, POST | 내 입력 이력 / CSV 검증 |
| `/api/v1/uploads/{id}` | GET | 내 입력 상세 |
| `/api/v1/analyses` | POST | durable Job 등록; Idempotency-Key 필요 |
| `/api/v1/jobs`, `/jobs/{id}` | GET | 내 작업 이력·상태 |
| `/api/v1/jobs/{id}/retry` | POST | 허용된 실패 작업의 bounded retry |
| `/api/v1/jobs/{id}/stream` | GET | 저장 상태 기반 SSE |
| `/api/v1/jobs/{id}/results`, `/results.csv` | GET | 저장 결과·CSV |
| `/api/v1/admin/metrics` | GET | 관리자만 운영 지표 |

쿠키 인증의 상태 변경에는 `X-CSRF-Token`을 보낸다. 이 값은 현재 세션과 결합된 읽기 가능한 CSRF 쿠키에서 얻으며 인증 세션은 HttpOnly다. 날짜 범위/숫자/schema는 Pydantic으로 검증한다. 오류는 `error.code`, 안전한 message, request_id를 사용하며 401/403/404/409/422/503을 구분한다.

Job 생성 예: `POST /api/v1/analyses`에 `{"upload_id":"..."}`와 고유 Idempotency-Key를 전송한다. broker가 실패하더라도 DB의 QUEUED/pending_dispatch와 Job ID를 유지하고 bounded 복구한다. 성공 결과의 숫자 표시 값은 DEMO/FIXTURE다.
