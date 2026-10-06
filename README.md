# adsp-study-rag

ADsP 교재를 근거로 질문에 답하는 시험공부용 RAG입니다. 질문하면 교재에서 근거를 찾아 답과 근거 원문(책·쪽)을 함께 보여 주고, 근거가 부족하면 "자료에서 확인 불가"로 답합니다.

> **개인 학습용입니다. 외부 배포 금지.** 교재·강의자료(이미지·텍스트)는 저작권이 있으므로 `data/`(gitignore)에만 두고 커밋하지 않습니다.

## 현재 상태 (2026-10-06)
- 팀 교재 3권(1·2·3과목) 324쪽을 반입·청킹·임베딩했습니다(검색 대상 청크 605개, BGE-M3).
- 질의 API `POST /qa`: 벡터 검색 → 리랭커(bge-reranker-v2-m3) → "확인 불가" 3구간 → Gemini 답변 + 인용 검증. 회색 구간만 판정기(Jev)를 부릅니다(꺼도 동작).
- 최소 공부 화면(`frontend/`): 질문 → 답·객관식 보기별 판단·근거 원문 카드.
- 평가: 검색 33문항(`eval/questions.csv`) hit@5 100%, 기출 객관식 15문제 맞음 12 / 틀림 0. 기준값은 33문항 기준 잠정값입니다.
- 다음 할 일: 팀원 정제 데이터(공통 JSON)로 재적재 → 기준값 재조정. 남은 작업은 GitHub Issues에서 관리합니다.

## 설치
- **Python 3.12 + [uv](https://docs.astral.sh/uv/)**: 패키지는 uv로만 관리합니다(pip 직접 사용 금지).
  ```powershell
  uv sync
  ```
- **Node.js 22.12 이상**(Vite 8): `cd frontend; npm ci`
- **모델 캐시**(처음 실행 시 자동 다운로드, 위치는 `.env`):
  - 임베딩(BAAI/bge-m3) + 리랭커(BAAI/bge-reranker-v2-m3): 약 8.5GB → `EMBEDDING_MODEL_DIR`
  - PaddleOCR(새 캡처 업로드용): 약 19MB → `OCR_MODEL_DIR`
  - **C 드라이브 여유가 적으면** 모델 경로와 uv 캐시(`UV_CACHE_DIR` 사용자 환경변수)를 다른 드라이브로 옮기세요. `.env.example`의 `E:\…` 경로는 예시이므로 각자 고칩니다.

## .env
1. `.env.example`을 `.env`로 복사합니다(프론트는 `frontend/.env.example` → `frontend/.env`, 기본값 그대로 써도 됨).
2. `GEMINI_API_KEY`: 각자 발급해 넣습니다(무료 한도가 작으니 질문 수를 아껴 주세요).
3. DB 접속 정보(`DB_HOST`, `DB_USER`, `DB_PASSWORD`)와 TypeSafe 키는 **민규가 따로 전달**합니다. 채팅·Issue·PR에 붙여 넣지 마세요.
4. 판정기는 기본 `JUDGE_PROVIDER=none`입니다(키 없이도 전체 서비스가 동작).

## 실행
```powershell
# 백엔드 (시작할 때 임베딩·리랭커를 올려서 약 1분, RAM 약 4.7GB)
cd backend; uv run uvicorn app.main:app --reload
# → http://127.0.0.1:8000/docs (API 문서: docs/API.md)

# 프론트 (백엔드를 먼저 켜 두세요)
cd frontend; npm run dev
# → http://localhost:5173
```

## 테스트
```powershell
uv run pytest                     # 기본: 가짜 모델로 빠르게
uv run pytest -m embedding_model  # 실제 BGE-M3 (느림)
uv run pytest -m reranker_model   # 실제 리랭커 (느림)
uv run pytest -m ocr_model        # 실제 PaddleOCR (느림)
cd frontend; npm run lint; npm run build
```
- DB 테스트는 `.env`의 DB에 접속될 때만 돌고, 접속이 안 되면 건너뜁니다. CI에는 DB 정보를 넣지 않으므로 **DB 관련 변경은 PR 전에 로컬에서** DB 테스트까지 돌려 주세요.

## 폴더 구조
```
backend/app/        FastAPI 앱 (api, ingestion, retrieval, qa, judge, llm, repositories, storage, prompts)
backend/migrations/ 서비스 스키마 DDL (번호 붙은 SQL)
backend/tests/      pytest
frontend/           React + Vite + TypeScript 화면
eval/               평가 세트 (질문 + 정답 쪽번호만, 교재 원문 없음. 비공개 세트는 eval/private/ — gitignore)
scripts/            보조 스크립트 자리
docs/               ARCHITECTURE(구조) · DECISIONS(결정 기록) · PROJECT(요구사항) · API · MODIFY_GUIDE(수정 위치 표) · guides/(기술 메모)
data/               교재·추출 결과·보고서 (gitignore, 커밋 금지)
```

## 역할
| 역할 | 담당 | 주로 보는 곳 |
|---|---|---|
| DB·재적재·DDL 적용·질의 흐름 | 민규 | `backend/migrations/`, `backend/app/ingestion/`, `backend/app/qa/` |
| 데이터(교재 정제 → 공통 JSON) | (이름) | 공통 JSON 형식, `data/`(로컬) |
| 프론트 | (이름) | `frontend/`, `docs/API.md` |
| 백엔드 기능 | (이름) | `backend/app/`, `docs/API.md` |

## 브랜치·PR 규칙 (팀 약속)
- **main에 직접 push 금지.** 무료 비공개 저장소라 GitHub 보호 브랜치를 쓸 수 없어서 약속으로 지킵니다.
- 작업 순서: `git fetch` → 최신 main에서 기능 브랜치(`feat/…`, `fix/…`, `docs/…`, `chore/…`) → 커밋 → push → PR(관련 Issue 번호 적기) → **CI(pytest, 프론트 lint·build) 통과 후** 머지.
- 커밋 메시지: `feat:`, `fix:`, `docs:`, `chore:` + 한국어 설명.
- API(요청·응답)를 바꾸는 PR은 `docs/API.md`도 같이 고칩니다. 중요한 결정은 `docs/DECISIONS.md`에 이니셜 번호(`D-<이니셜>-<번호>`, 맨 위 규칙 참고)로 남깁니다.
- Claude Code를 쓴다면 팀 규칙은 `CLAUDE.md`, 개인 지침은 각자 `CLAUDE.local.md`(gitignore)에 둡니다.

## DB 규칙 (공유 서버)
- 서비스 스키마는 `mingyu`(팀 규격 테이블) · `mingyu_app`(앱 전용)입니다. 이름은 `.env`(`DB_SCHEMA`, `DB_APP_SCHEMA`)에서만 읽고 코드에 쓰지 않습니다.
- 각자 실험용 스키마는 본인만 씁니다. public과 다른 사람 스키마는 읽지도 쓰지도 않습니다.
- 서비스 스키마 변경은 `backend/migrations/` 번호 파일 + PR + 팀 공지로만 합니다. **재적재와 DDL 적용은 민규만** 합니다. 팀 규격 테이블의 기존 컬럼은 이름 변경·삭제·타입 변경 금지(추가만).
- 데이터 담당 결과물은 DB가 아니라 공통 JSON 파일로 받습니다. 기출은 DB에 넣지 않습니다.
- DB 서버는 보안 그룹으로 **팀원 IP만 허용**합니다(민규가 AWS에서 설정). IP가 바뀌면 민규에게 알려 주세요.

## 저작권·보안
- 교재 원문(이미지·텍스트·OCR 결과)과 기출 원문은 커밋하지 않습니다. `.gitignore`에 `data/`, `*.ocr.json`, `*.text.json`, `eval/private/`가 들어 있습니다.
- 비밀정보(DB 비밀번호, API 키)는 `.env`에만 둡니다. 코드·로그·커밋·PR·Issue에 남기지 않습니다.
