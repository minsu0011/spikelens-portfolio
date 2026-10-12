# 비동기 처리와 복구

상태: QUEUED → RUNNING → SUCCEEDED 또는 FAILED. 재시도가 허용된 FAILED는 QUEUED로 돌아간다. CANCELLED는 구현하지 않았다.

`services/jobs.py::create_job`은 입력 소유권·검증 상태를 확인하고 DB transaction을 commit한다. `dispatch_one`은 별도 2초 연결/socket timeout, 초기 ensure retry 0, publication retry=False와 ignore_result=True를 사용한다. task 결과 backend 구독을 요구하지 않으며 worker의 정상 broker 재연결은 유지한다.

`claim_job`은 row lock으로 하나의 유효 claim과 lease token을 만든다. `tasks/analysis.py::process_job`은 SHA 검증 후 CSV를 다시 확인한다. 공개 provider는 fixture와 품질 집계만 반환한다. 100행 batch마다 결과와 처리 건수·lease를 함께 저장한다. 각 batch와 완료 commit은 fencing token을 검사한다. 마지막 저장 전에 실패하거나 old worker가 복귀해도 중복 결과 UNIQUE와 token 검사가 정합성을 보호한다.

beat는 미전달/미claim 작업과 만료 lease를 복구한다. 처리 시도 최대 3회, dispatch 최대 5회와 backoff를 적용한다. 실패 상태가 저장될 수 없는 DB 장애에서는 만료 lease가 복구의 기준이다. API에서 임의 완료 상태로 변경하지 않는다.

SSE snapshot은 짧은 DB session을 사용한다. async loop와 heartbeat를 유지하며 인증/소유권·세션 유효성을 확인한다. UI는 SSE 연결이 실패할 때 실제 GET job polling을 사용한다. 진행률은 worker가 DB에 기록한 처리 건수다.

검증: 16개 동시 등록, 실제 Celery subprocess 종료와 lease 복구, 완료 직전 예외, 재시도 소진, TCP 연결 거부, 실제 공개 컨테이너 중단·복구와 2,000행 브라우저 흐름. 최신 결과를 `docs/evidence`에서 확인한다.
