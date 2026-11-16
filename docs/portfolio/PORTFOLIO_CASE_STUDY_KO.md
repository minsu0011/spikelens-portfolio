# SpikeLens 포트폴리오 설명

CSV 이벤트를 업로드하면 실제 PostgreSQL Job과 Redis 메시지가 만들어지고 Celery가 데이터를 처리한다. UI에서 DB 진행률과 결과를 조회한다. 목적은 예측 모델의 성능이 아니라 API·인증·정합성·비동기 작업·복구·운영 관찰의 구현을 설명하는 것이다.

공개본은 모델 구현을 제거한 별도 snapshot이다. 공개 fixture와 데이터 품질만 반환하지만 업로드→큐→worker→저장→SSE/조회 경로는 실제로 동작한다. 원본의 Git history와 내부 자료를 가져오지 않고 새 공개 작업부터 commit한다.

핵심 사례는 owner/idempotency UNIQUE와 16개 동시 요청, row lock/lease/fencing, batch 결과 저장과 제한된 retry, Redis 장애 중 durable outbox, 공유 proxy 뒤 계정별 로그인 제한, 파일 fsync 실패와 원자적 게시다. 관련 실제 테스트는 `backend/tests/test_integration.py`, `test_publisher_integration.py`에 있다.

테스트·브라우저·중단 복구·성능의 보존 기록은 `docs/evidence`에 있다. 이 프로젝트의 공개 범위는 합성 데모와 로컬 실행이다.

작성에는 AI/Codex의 도움을 받았다.
