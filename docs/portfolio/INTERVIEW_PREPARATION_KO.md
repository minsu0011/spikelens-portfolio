# 공개 코드와 연결한 면접 준비

| 질문 | 실제 구현과 설명 |
|---|---|
| 로그인 내부 흐름 | `api/auth.py`, `core/security.py`: Argon2 검증, opaque token, DB digest, HttpOnly/CSRF cookie |
| 세션과 JWT 차이 | DB 세션은 logout/만료를 서버에서 무효화한다. 이 프로젝트는 JWT를 사용하지 않는다. |
| ORM과 DB 연결 | `db/session.py`의 SQLAlchemy Session/pool과 `models/entities.py`의 ORM 매핑 |
| 트랜잭션 필요성 | Job 및 audit와 결과 batch/진행률의 정합성; 메시지 게시와 DB commit은 다른 실패 구간 |
| CSV→Job | `api/uploads.py`/`services/csv_validation.py`/`api/jobs.py`: validation·SHA·소유권·Job commit |
| Redis와 Celery | broker 전송·캐시와 worker task 실행의 역할을 분리한다. |
| Worker 중간 종료 | lease 만료 후 재claim; `fenced_job`으로 오래된 token의 쓰기를 거부한다. |
| Idempotency | `create_job`의 owner/key 및 upload/provider UNIQUE, 같은 요청 반환과 다른 입력 conflict |
| Race condition | 16개 요청 동시 생성, row lock, UNIQUE, advisory lock과 실제 테스트 |
| Cache | 공개 summary key/TTL/무효화·DB fallback; 비공개 요약은 공유하지 않는다. |
| SSE와 WebSocket | 단방향 상태 전달에 SSE 사용, 연결 실패는 실제 polling으로 복구 |
| 인덱스 | 종목/세션/시간과 owner 인덱스, 임시 합성 테이블의 EXPLAIN 비교 |
| Docker 통신 | Compose DNS와 내부 포트, loopback published port, 독립 네트워크/볼륨 |
| GitHub Actions | safety/backend/frontend/Docker-E2E 4개 job. 실제 공개 저장소의 commit별 Actions 결과를 확인한다. service healthcheck 인자 해석 오류도 원격 로그로 확인하고 수정했다. |
| 실제 장애와 한계 | `PUBLIC_RUNTIME_QA.json`의 실제 Redis/worker/DB 중단, 제한된 게시와 outbox 복구. 운영을 수행했다고 과장하지 않는다. |

공개 provider는 `providers/base.py`/`demo.py`의 데이터 품질 계약과 fixture만 설명한다. 비공개 모델 내부 구현은 설명 자료에 포함하지 않는다.
