# 2026-09-30 설계 문서 보완 + 사용자용 문서 (코드 변경 없음)

## 무엇을 만들었나
- **설계 보완**: 오답노트(내 답·내 이유 입력 → 근거와 비교 → 틀린 유형 분류 → 저장 → 재질문), 품질 검수 도구(HTML 보고서 → 관리 화면 검수 탭), 시각자료 표시 원칙(그래프를 다시 그리지 않고 원본 crop + 설명문)을 설계 문서에 넣었다.
- **팀 교재 데이터 계획**: `data/raw/adsp/`의 스캔 PDF 3권과 팀원이 추출한 텍스트를 어떻게 반입할지(파일명 정리 → 쪽 매핑 → books/pages 생성 → 팀 텍스트를 추출 결과로 저장)와 3과목 그림·표를 잘라내는 계획을 정했다. 다음 작업 순서도 9단계로 다시 정리했다.
- **사용자용 문서와 규칙**: 백엔드 전체 설명서(`docs/sessions/00-overview.md`), "무엇을 바꾸려면 어디를 고치나" 표(`docs/MODIFY_GUIDE.md`)를 만들었다. CLAUDE.md에 "조정할 값은 `.env`/`config.py` 한 곳, 프롬프트는 `backend/app/prompts/` 텍스트 파일" 규칙을 넣고, `/wrap`이 세션마다 이런 설명 파일을 남기도록 바꿨다.

## 어떻게 돌아가나
이번 세션은 코드를 바꾸지 않았으므로 서버 동작은 지난 세션과 같다(흐름 전체는 `00-overview.md` 3장 참고).

바뀐 것은 문서와 작업 방식이다. 새 세션을 `/start`로 시작하면 Claude는 `docs/PROGRESS.md` → `DECISIONS.md` → `ARCHITECTURE.md`를 읽는다. `docs/sessions/`와 `MODIFY_GUIDE.md`는 사용자용이라 읽지 않는다. PROGRESS의 "다음 작업" 1번(팀 교재 반입)에는 할 일, 관련 파일, 주의점이 적혀 있다. 세션을 끝낼 때 `/wrap`을 부르면 테스트 → PROGRESS 갱신 → 설계 문서 갱신 → `docs/sessions/날짜-주제.md` 작성 → 커밋 순서로 진행된다.

설계 내용은 다음 위치에 있다.
- `docs/ARCHITECTURE.md`: "팀 교재 반입 경로", "시각자료 crop 파이프라인", "품질 검수 도구", "시각자료 표시 원칙", "오답노트"(mingyu_app 테이블 초안), 판정기 역할 추가(`reason_match`, `error_type`)
- `docs/DECISIONS.md`: D-014(팀 텍스트 사용), D-015(시각자료 표시), D-016(crop 파이프라인), D-017(오답노트)

설계를 쓰면서 DB에서 읽기만 해서 확인한 사실도 있다. `confusable_concepts`와 `exam_clues`는 `mingyu.theory_chunks`의 JSONB 컬럼이다. `v_review_queue`는 페이지 단위 뷰다. `pages.printed_page_number` 컬럼이 이미 있다.

## 직접 확인하는 방법
1. 문서 읽기
   - `docs/sessions/00-overview.md`: 백엔드가 어떻게 돌아가는지, 서버를 켜고 `/docs`와 DataGrip으로 확인하는 방법
   - `docs/MODIFY_GUIDE.md`: 값을 바꾸고 싶을 때 열 파일
   - `docs/PROGRESS.md`의 "다음 작업": 다음 세션에서 할 일
2. 테스트 (코드가 그대로인지 확인)
   ```powershell
   cd E:\자료실\adsp-study-rag
   uv run pytest
   ```
   기대 결과: `43 passed, 1 deselected` (deselected 1개는 실제 OCR 모델 테스트로, `-m ocr_model`로 따로 실행)
3. DataGrip (설계에 쓴 컬럼 확인, 선택)
   ```sql
   SELECT column_name, data_type FROM information_schema.columns
   WHERE table_schema = 'mingyu' AND table_name = 'theory_chunks'
     AND column_name IN ('exam_clues', 'confusable_concepts');
   ```
   기대 결과: 두 행, 둘 다 `jsonb`
4. GitHub: `Yubeol/study-ai-solver`의 main에서 커밋 `332a69b`, `631f381`이 보이면 push 완료

## 아직 안 되는 것
- 설계만 했고 구현은 없다: 팀 교재 반입, crop, 검수 보고서, 오답노트(mingyu_app 테이블도 아직 안 만듦)
- 확인 필요: 팀 텍스트 1·3과목이 1쪽씩 부족한 이유, Jev 키 경로(TypeSafe 직접 / Cloudflare), 레이아웃 모델의 Windows + CPU 동작 여부
- `.env.example`에 Jev 설정 이름(`JEV_ENABLED`, `JEV_MODEL`, `JEV_TIMEOUT_SECONDS`)이 아직 없다(Jev 연동 때 추가)
- 커넥션 풀 크기(1/5)는 새 규칙과 달리 아직 코드 상수(`backend/app/db/connection.py`)
