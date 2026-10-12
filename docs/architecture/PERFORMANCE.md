# 공개본의 실제 로컬 측정

공개 Demo Provider로 생성한 합성 이벤트 10,000건, 로컬 Windows→WSL2 Linux Docker loopback, 7950X/48GB 환경에서 측정했다. 같은 PC의 다른 작업도 실행 중이었다. endpoint당 200요청, 동시성 8, warmup 5회 제외이며 p95는 정렬 표본의 floor((N-1)×0.95)다.

| 조회 | p50 ms | p95 ms | req/s |
|---|---:|---:|---:|
| 최근 이벤트 | 39.575 | 51.655 | 194.570 |
| 종목 필터 | 37.160 | 46.325 | 214.349 |
| 세션 필터 | 37.749 | 52.371 | 206.744 |
| 캐시 요약 | 13.701 | 17.640 | 568.715 |

직렬 20쌍 비교에서 캐시 miss p50 12.559ms, 즉시 hit p50 2.028ms였다. 공개 summary 키만 삭제하며 broker와 Redis DB 전체를 비우지 않았다. 공유 캐시는 공개 데이터에만 적용한다.

인덱스 비교는 합성 공개 데이터의 id/time/ticker/session만 복사한 TEMP TABLE에서 각각 10회 EXPLAIN ANALYZE했다. 인덱스 전 median 0.364ms, 후 0.032ms였다. 운영 테이블 인덱스는 삭제하지 않았고 TEMP TABLE은 transaction 종료 때 제거된다. API는 offset pagination이며 keyset API를 구현했다고 주장하지 않는다.

명령: 프로젝트 루트에서 `python scripts/benchmark_public.py`. 로컬 `.env`에 독립 Demo DB/Redis 연결값이 필요하다. 결과 [PUBLIC_PERFORMANCE.json](../evidence/PUBLIC_PERFORMANCE.json)에 원시 실행시간과 실제 plan을 저장한다. 이 작은 표본은 운영 SLO·최대 처리량·장애율이나 실제 서비스 운영 경험을 의미하지 않는다. 원본 private 개발의 성능 기록을 재사용하지 않았다.
