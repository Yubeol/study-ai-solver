# CLAUDE.md — adsp-study-rag 팀 개발 규칙

개인 지침(세션 시작·완료 루틴, 개인 경로, 개인 명령)은 각자 저장소 루트의 `CLAUDE.local.md`(gitignore)에 둔다.

## 작업 범위
- 한 브랜치(PR)는 하나의 기능/목표만 다룬다. 요청하지 않은 기능 추가나 대규모 리팩터링을 하지 않는다.
- 구현 전에 관련 코드를 먼저 읽는다. 확인하지 않은 내용은 추측하지 않고 모른다고 말한다.
- 최신 정보가 필요한 API, 가격, 모델, SDK는 공식 자료로 확인하고, 확인 날짜와 출처 URL을 `docs/DECISIONS.md`에 남긴다. 특히 Jev 관련 정보는 절대 추측하지 않는다.

## 브랜치·PR
- main에 직접 커밋·push하지 않는다. 기능 브랜치(`feat/…`, `fix/…`, `docs/…`, `chore/…`) → PR → CI(pytest, 프론트 lint·build) 통과 → 머지.
- 작업 전 `git fetch` 후 최신 main에서 브랜치를 만든다. 남은 작업은 GitHub Issues로 관리하고, PR 설명에 관련 Issue 번호를 적는다.
- 커밋 메시지는 `feat:`, `fix:`, `docs:`, `chore:` 접두어 + 한국어 설명.

## 환경
- OS: Windows, 셸: PowerShell. 프로젝트 경로에 한글이 들어갈 수 있다.
- Python 3.12 고정(`.python-version`), 패키지는 uv로만 관리한다: `uv add <pkg>`, `uv run <cmd>`. pip를 직접 쓰지 않는다.
- 루트의 `pyproject.toml`과 `.venv`가 백엔드 환경이다. 백엔드 코드는 `backend/`, 프론트엔드는 `frontend/`(React + Vite).
- 응답과 문서는 한국어로 작성한다.

## 한글 경로 규칙 (필수)
- OpenCV로 파일을 열 때 `cv2.imread(path)`를 쓰지 않는다. `np.fromfile(path, dtype=np.uint8)` 후 `cv2.imdecode`를 쓴다. 저장은 `cv2.imencode` 후 바이트로 쓴다.
- 경로는 `pathlib.Path`로 다루고, 텍스트 파일은 항상 `encoding="utf-8"`로 읽고 쓴다.

## DB 규칙 (공유 서버)
- DB는 팀 공유 서버(`cert_rag`)다. 서비스 스키마는 `.env`의 `DB_SCHEMA`(mingyu)와 `DB_APP_SCHEMA`(mingyu_app)다. public과 다른 사람의 실험용 스키마는 읽지도 쓰지도 않는다. 각자 실험용 스키마는 본인만 쓴다.
- 서비스 스키마 변경(DDL)은 `backend/migrations/`의 번호 붙은 SQL 파일 + PR + 팀 공지로만 한다. 재적재와 DDL 적용은 민규만 한다. 적용 전에 내용을 보여주고 확인받는다.
- 스키마 이름을 코드에 하드코딩하지 않고 설정값에서만 가져온다.
- 세션 단위 `SET search_path`를 쓰지 않는다(커넥션 풀에서 다른 요청으로 새어 나간다). 트랜잭션 안의 `SET LOCAL` 또는 스키마를 명시한 쿼리를 쓴다.
- 팀 규격 테이블의 기존 컬럼은 이름 변경·삭제·타입 변경을 하지 않는다. 필요한 것은 컬럼/인덱스 추가만 한다.
- `theory_chunks.raw_text`는 교재 원문 그대로 저장한다. 일반 지식으로 자동 교정하지 않는다.
- 데이터 담당 결과물은 DB가 아니라 공통 JSON 파일로 주고받는다. 기출은 DB에 넣지 않는다(평가 파일로만).

## 외부 모델 규칙
- 모델 이름은 코드에 하드코딩하지 않고 `.env` 설정값을 쓴다.
- 판정기(Jev)는 교체 가능한 모듈이다. `JUDGE_PROVIDER=none`에서도 전체 서비스가 끝까지 동작해야 한다.
- 답변은 검색된 근거로만 만든다. 근거가 부족하면 "자료에서 확인 불가"로 답한다.

## 조정 가능한 값 / 프롬프트
- 나중에 직접 조정할 만한 값(모델명, 청크 크기, 검색 개수, crop 여백, 임계값, 재시도 횟수 등)은 코드에 하드코딩하지 않고 `.env` 또는 `backend/app/core/config.py` 한 곳에 둔다. 새 값을 추가하면 `.env.example`과 `docs/MODIFY_GUIDE.md`도 같이 고친다.
- LLM 프롬프트 문장은 코드 안 문자열로 두지 않고 `backend/app/prompts/` 아래 별도 텍스트 파일(UTF-8)로 둔다. 코드는 파일을 읽어 변수만 채운다.

## 문서
- `docs/DECISIONS.md` 번호: D-001~D-029는 팀 합류 전 기록으로 그대로 둔다. 새 결정은 `D-<이니셜>-<번호>`로 각자 따로 번호를 이어 간다(민규 `D-M-030`부터, 팀원은 각자 `001`부터, 예: `D-J-001`). 이니셜이 겹치면 두 글자로 정한다.
- `docs/ARCHITECTURE.md`, `docs/MODIFY_GUIDE.md`, `docs/API.md`는 내용이 실제로 바뀐 경우에만 같은 PR에서 고친다. API(요청·응답)를 바꾸는 PR은 `docs/API.md`를 반드시 같이 고친다.

## 보안 / 저작권
- 비밀정보는 `.env`에만 둔다. 코드, 로그, 커밋, 테스트 출력, PR·Issue에 키나 비밀번호를 남기지 않는다.
- 교재·강의자료 이미지와 텍스트는 `data/`(gitignore)에만 두고 커밋하지 않는다. 개인 학습 목적, 외부 배포 금지.

## 작업 완료 루틴
1. 관련 테스트를 실행한다(`uv run pytest`, 프론트를 바꿨으면 `cd frontend; npm run lint; npm run build`).
2. `git status`로 변경 파일을 확인한다.
3. 위 "문서" 규칙에 따라 필요한 문서만 고친다. 중요한 결정은 DECISIONS에 이니셜 번호로 남긴다.
4. 기능 브랜치에 커밋하고 push한 뒤 PR을 연다. main 머지는 CI 통과 후.
