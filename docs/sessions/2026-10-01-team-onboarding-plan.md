# 2026-10-01 팀 합류 준비 — 저장소 정리 조사·계획

## 무엇을 만들었나
코드나 파일 구조는 바꾸지 않았다. 팀원 3명이 이 저장소로 합류하기 전에, 무엇을 공유하고 무엇을 빼야 하는지 조사하고 정리 계획을 세웠다. 조사 결과와 사용자 결정(A~D)은 `docs/PROGRESS.md` "다음 작업" 1번과 `docs/DECISIONS.md` D-030에 남겼다.

## 어떻게 돌아가나(조사한 순서)
먼저 `git ls-files`로 지금 GitHub에 올라가는 파일 121개를 뽑아 네 묶음으로 나눴다. 코드·설정 예시·테스트는 팀 공유, ARCHITECTURE·DECISIONS·MODIFY_GUIDE·PROJECT·docs/team은 팀 문서, PROGRESS·docs/sessions·/start·/wrap 명령은 개인용, 교재 원문은 모두 `data/` 안에 있어 올라가는 것이 없었다.

다음으로 커밋 기록 전체(39개)를 훑었다. 한 번이라도 추가된 파일 경로 중에 `data/`나 `.env`는 없었고, `.env`에 들어 있는 실제 비밀값(DB 주소·계정·비밀번호, Gemini·TypeSafe 키)이 기록에 나타난 횟수를 세어 보니 모두 0이었다(값은 화면에 찍지 않고 개수만 셈). 그래서 기록을 다시 쓸 필요 없이, 개인 문서를 앞으로 올라가지 않게 "추적 해제"만 하면 된다.

그다음 GitHub Actions(자동 테스트)에서 어떻게 될지 보려고, DB에 닿지 않는 가짜 주소로 테스트를 돌렸다. DB가 필요한 테스트는 대부분 스스로 건너뛰었지만 2개가 실패했다. 이 둘은 DB가 없을 때 건너뛰게 고쳐야 CI를 켤 수 있다. 실제 모델(임베딩·리랭커·OCR)이 필요한 테스트는 원래 기본 실행에서 빠져 있고, 나머지는 가짜 모델을 쓰므로 CI가 모델 파일 8GB를 받을 일은 없다. 다만 Linux에서는 torch가 GPU용으로 설치돼 무거우므로 CPU용으로 바꾸는 작업을 별도로 하기로 했다.

마지막으로 Claude Code 지침 파일을 팀용(`CLAUDE.md`, 공유)과 개인용(`CLAUDE.local.md`, 공유 안 함)으로 나누는 방법, README 목차, CI 설정 초안, API 문서(`docs/API.md` + FastAPI `/docs`) 방안을 정했다.

## 직접 확인하는 방법
- 계획 읽기: `docs/PROGRESS.md`의 "다음 작업" 맨 위 "[다음 세션 1번: 팀 합류 준비 저장소 정리]"와 "[다음 세션 2번: 재적재]", `docs/DECISIONS.md` 맨 아래 D-030
- 지금 GitHub에 올라가는 파일 목록: PowerShell에서 `git ls-files` → 121개, `data/`로 시작하는 줄이 없어야 함
- 기록에 data/·.env가 없는지: `git log --all --name-only --pretty=format: | Select-String "^data/|\.env$"` → 아무것도 안 나와야 함
- CI와 같은 조건의 테스트(DB 없음): `$env:DB_HOST='127.0.0.1'; $env:DB_PORT='1'; uv run pytest -q` → 106 통과, 19 건너뜀, 2 실패(`test_pool_connection_does_not_leak_search_path`, `test_qa_api`). 새 PowerShell 창에서 하거나 끝난 뒤 `Remove-Item Env:DB_HOST, Env:DB_PORT`
- 평소 테스트: `uv run pytest` → 127 통과

## 아직 안 되는 것
- 계획만 세웠고 실제 정리(.gitignore 수정, 추적 해제, CLAUDE.md 분리, README·API.md 작성, 테스트 2개 수정, CI 추가)는 다음 세션에 `chore/team-onboarding` 브랜치에서 한다
- torch CPU 인덱스 적용은 정리 PR 머지 뒤 별도 PR
- GitHub Issues 목록은 사용자가 웹에서 직접 만든다
- 재적재(팀원 공통 JSON)는 형식 샘플을 받은 뒤 조사
