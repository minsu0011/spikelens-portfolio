# 공개 데모 장애 대응

| 상황 | 확인 | 복구와 검증 |
|---|---|---|
| PostgreSQL 연결 실패 | live200/ready503, 연결·migration·volume 상태 | DB 복구 후 ready200, 원래 작업과 결과 조회 |
| Redis 연결 실패 | ready503, 공개 summary DB fallback, pending_dispatch | Redis 복구 후 beat의 제한된 재게시와 같은 Job 결과 확인 |
| Worker 중단 | QUEUED 또는 lease가 만료되는 RUNNING | worker 재시작, fencing/unique 결과로 중복 없이 완료 |
| Queue 정체 | queue wait, worker ping, pending_dispatch와 retry 횟수 | 원인 복구; 임의 SUCCEEDED 변경 금지 |
| Migration 실패 | backend start 실패, Alembic current/DB 상태 | 별도 백업·복원·upgrade 검증 후 재시작 |
| 잘못된 CSV | validation_errors, 파일/행 제한 및 schema | 입력 수정 후 새 업로드; invalid 상태로 task 생성 금지 |
| 중복 등록 | UNIQUE/Idempotency conflict409 또는 같은 Job 반환 | key와 입력의 관계 확인; 중복 결과 insert 금지 |
| API 지연 | request_id, 최근 p50/p95, DB plan/캐시/connection | 실제 표본과 쿼리 확인 후 개선; 운영 SLO로 과장 금지 |

`scripts/runtime_smoke.py`는 이 public Compose 프로젝트만 대상으로 Redis·worker·DB를 실제 stop/start한다. 각 중단은 finally에서 복구한다. 사용 중인 로컬 데모에서 실행하면 일시적으로 요청이 실패할 수 있다. 실행 증거는 `PUBLIC_RUNTIME_QA.json`이다. 실제 계정/쿠키/연결 문자열을 로그나 screenshot에 노출하지 않는다.
