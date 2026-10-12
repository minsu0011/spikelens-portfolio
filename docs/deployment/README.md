# 공개 운영 전에 남은 작업

현재는 loopback Synthetic Demo다. GitHub 소스 공개와 cloud 서비스 배포를 구분한다. Cloud 계정 연결과 과금은 수행하지 않았다.

HTTPS/Secure cookie와 정확한 운영 Origin·신뢰 proxy, 이메일 인증·비밀번호 재설정, 최소 권한 DB·Redis ACL/TLS, 비밀값 관리자, durable 업로드 저장소와 DB/파일 동시 백업·복원 실험, 중앙 로그·메트릭·경보, quota·보존 정책·동시 worker 부하를 준비한다. 단일 beat와 배포 drain/lease 복구를 검증한다.

현재 GitHub Actions는 파일 정의와 로컬 동등 검사만 수행했다. 실제 원격 결과는 승인 후 push한 workflow run을 확인해야 한다. 프로젝트 라이선스는 아직 별도 지정하지 않았으며 임의 MIT 사용 허가를 추가하지 않는다.
