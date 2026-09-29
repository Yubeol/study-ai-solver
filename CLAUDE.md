# CLAUDE.md — adsp-study-rag 개발 규칙

## 세션 시작 루틴
1. `docs/PROGRESS.md` → `docs/DECISIONS.md` → `docs/ARCHITECTURE.md` 순서로 읽는다. 요구사항이 필요하면 `docs/PROJECT.md`를 읽는다.
2. 필요하면 `git status`, `git log --oneline -10`으로 코드 상태를 확인한다.
3. 현재 상태를 3~5줄로 요약한 뒤, 사용자가 요청한 작업만 진행한다.

## 작업 범위
- 한 세션은 하나의 기능/목표만 다룬다. 요청하지 않은 기능 추가나 대규모 리팩터링을 하지 않는다.
- 구현 전에 관련 코드를 먼저 읽는다. 확인하지 않은 내용은 추측하지 않고 모른다고 말한다.
- 최신 정보가 필요한 API, 가격, 모델, SDK는 공식 자료로 확인하고, 확인 날짜와 출처 URL을 `docs/DECISIONS.md`에 남긴다. 특히 Jev 관련 정보는 절대 추측하지 않는다.

## 환경
- OS: Windows, 셸: PowerShell. 프로젝트 경로에 한글(`E:\자료실\...`)이 포함되어 있다.
- Python 3.12 고정(`.python-version`), 패키지는 uv로만 관리한다: `uv add <pkg>`, `uv run <cmd>`. pip를 직접 쓰지 않는다.
- 루트의 `pyproject.toml`과 `.venv`가 백엔드 환경이다. 백엔드 코드는 `backend/`, 프론트엔드는 `frontend/`(React + Vite).
- 응답과 문서는 한국어로 작성한다.

## 한글 경로 규칙 (필수)
- OpenCV로 파일을 열 때 `cv2.imread(path)`를 쓰지 않는다. `np.fromfile(path, dtype=np.uint8)` 후 `cv2.imdecode`를 쓴다. 저장은 `cv2.imencode` 후 바이트로 쓴다.
- 경로는 `pathlib.Path`로 다루고, 텍스트 파일은 항상 `encoding="utf-8"`로 읽고 쓴다.

## DB 규칙 (공유 서버)
- DB는 팀 공유 서버(`cert_rag`)다. 수정 가능한 스키마는 `.env`의 `DB_SCHEMA`(mingyu)와 `DB_APP_SCHEMA`(mingyu_app)뿐이다. 다른 팀원 스키마(jaewon, sugi, sumin)와 public은 읽지도 쓰지도 않는다.
- 스키마 이름을 코드에 하드코딩하지 않고 설정값에서만 가져온다.
- 세션 단위 `SET search_path`를 쓰지 않는다(커넥션 풀에서 다른 요청으로 새어 나간다). 트랜잭션 안의 `SET LOCAL` 또는 스키마를 명시한 쿼리를 쓴다.
- 팀 규격 테이블의 기존 컬럼은 이름 변경·삭제·타입 변경을 하지 않는다. 필요한 것은 컬럼/인덱스 추가만 한다.
- DDL 변경은 `backend/migrations/`의 번호 붙은 SQL 파일로만 한다. 적용 전에 사용자에게 내용을 보여주고 확인받는다.
- `theory_chunks.raw_text`는 교재 원문 그대로 저장한다. 일반 지식으로 자동 교정하지 않는다.

## 외부 모델 규칙
- 모델 이름은 코드에 하드코딩하지 않고 `.env` 설정값을 쓴다.
- 판정기(Jev)는 교체 가능한 모듈이다. `JUDGE_PROVIDER=none`에서도 전체 서비스가 끝까지 동작해야 한다.
- 답변은 검색된 근거로만 만든다. 근거가 부족하면 "자료에서 확인 불가"로 답한다.

## 보안 / 저작권
- 비밀정보는 `.env`에만 둔다. 코드, 로그, 커밋, 테스트 출력에 키나 비밀번호를 남기지 않는다.
- 교재·강의자료 이미지와 텍스트는 `data/`(gitignore)에만 두고 커밋하지 않는다. 개인 학습 목적, 외부 배포 금지.

## 작업 완료 루틴
1. 관련 테스트를 실행한다(`uv run pytest`).
2. `git status`로 변경 파일을 확인한다.
3. `docs/PROGRESS.md`를 갱신한다.
4. 아키텍처가 바뀌었으면 `docs/ARCHITECTURE.md`, 중요한 결정이 있었으면 `docs/DECISIONS.md`를 갱신한다.
5. 커밋한다. 메시지는 `feat:`, `fix:`, `docs:`, `chore:` 접두어 + 한국어 설명.