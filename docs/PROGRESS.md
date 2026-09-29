# PROGRESS

## 현재 상태 (2026-09-29)
- 1단계 완료: 저장소, uv 환경(Python 3.12 고정), .gitignore, GitHub 원격(study-ai-solver, private)
- 2단계 진행 중: .env / 운영 문서 5종 작성

## 다음 작업
1. 외부 접근 확인
   - Gemini 키로 gemini-2.5-flash-lite / gemini-2.5-flash 호출 가능한지 (막히면 3.1 Flash-Lite로 변경)
   - Jev: typesafe.ai 대기자 명단 신청, Cloudflare 계정 생성 후 typesafe/jev 무료 호출 가능 여부
   - S3: 팀 버킷 유무와 접근 방법 (없으면 STORAGE_BACKEND=local로 시작)
2. Claude Code 첫 세션: mingyu 스키마 보완 마이그레이션 + mingyu_app 생성 + FastAPI 골격 + DB 연결 테스트
3. 업로드 API + 백그라운드 처리 파이프라인

## 막힌 것 / 확인 필요
- S3 사용 가능 여부 미확인 (pages.source_s3_uri, visual_assets.crop_s3_uri가 NOT NULL)
- Gemini 2.5 신규 키 접근 가능 여부 미확인
- Jev Cloudflare 경로의 무료 할당량 적용 여부 미확인

## 일정
- 1주차 (09-29 ~ 10-04): 기반 + 업로드/처리 파이프라인(텍스트, 시각자료, 임베딩) + 검색 품질 확인
- 2주차 (10-05 ~ 10-11): 질의 흐름(판정, 제약 프리셋, 근거 표시) + 문제 사진 입력 + 화면 3개 + 실사용
- 여유분 (10-12 ~ 10-15), Gemini 2.5 종료(10-16) 전 완료

## 자체 평가 메모 (과제 성공 기준용, 실사용하며 기록)
- 실용성:
- 효율성:
- 미비점:
- 단점:

## 완료 기록
- 2026-09-29: 저장소 초기 구조, uv 환경, GitHub 연결