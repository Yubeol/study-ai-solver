# 2026-09-30 팀 교재 데이터 반입

## 무엇을 만들었나
- **팀 교재 반입 스크립트** (`backend/app/ingestion/team_import.py`)
  - 팀원이 공유한 ADsP 교재 PDF 3권과 페이지별 텍스트를 우리 DB에 넣는 명령줄 도구입니다.
  - 업로드 화면을 거치지 않습니다. 사진을 OCR하지 않고 팀원이 이미 뽑아 둔 텍스트를 "텍스트 추출 결과"로 씁니다.
  - 기본 동작은 **dry-run**(계획만 보여 주고 아무것도 바꾸지 않음)입니다. 실제로 넣으려면 `--apply --subject 과목`을 지정해야 합니다.
- **PDF 장 ↔ 교재 쪽번호 매핑 파일** (`data/raw/adsp/page_map.json`)
  - "PDF 몇 번째 장이 교재 몇 쪽인가"를 적어 둔 표입니다.
  - PDF 일부 장의 쪽번호를 이미지로 직접 대조해서 만들었습니다.
  - 3과목은 도중에 어긋나는 구간이 있어서 구간별로 따로 적었습니다. 216쪽은 촬영되지 않았고, 252쪽은 같은 사진이 두 번 들어 있습니다.
- **교재 3권 반입 완료**
  - pages 324행이 모두 `EXTRACTED` 상태로 들어갔습니다(1과목 50, 2과목 64, 3과목 210).
  - 페이지 이미지와 텍스트는 로컬 저장소에 있습니다(약 562MB).

## 어떻게 돌아가나
1. `python -m app.ingestion.team_import`를 실행하면 `main()`이 `data/raw/adsp/page_map.json`을 읽습니다(`load_map`).
2. 과목마다 `plan_book()`이 계획을 만듭니다.
   - 먼저 PDF를 열어 장 수를 셉니다. PDF 파일명이 macOS 방식(NFD)으로 저장돼 있어서 `resolve()`/`find_nfc()`가 이름을 맞춰 찾습니다. 파일을 여는 도구는 pypdfium2입니다.
   - 팀 텍스트 파일들은 UTF-8 원문 그대로 읽습니다(`read_texts`).
3. `build_plan()`이 실제 계획을 짭니다. DB나 파일은 건드리지 않습니다.
   - `pdf_to_printed()`: page_map의 구간 정보(segments)로 "PDF 장 → 쪽번호"를 계산합니다.
   - `text_file_pages()`: 텍스트 파일 이름(`과1-14p.txt` → 14쪽)으로 쪽을 연결합니다.
   - 두 쪽이 한 파일에 합쳐진 `과1-58-59p.txt`는 page_map에 적은 줄 번호(30번째 줄)에서 58쪽과 59쪽으로 나눕니다. 줄 단위로 자르기만 하고 글자는 바꾸지 않습니다(`slice_lines`).
   - 텍스트 끝의 쪽번호 줄과 매핑이 맞는지도 확인합니다(`footer_numbers`/`footer_matches`).
   - 계획은 화면에 요약되고 `data/reports/team_import/plan.json`에 저장됩니다.
4. `--apply`를 붙이면 `apply_book()`이 과목별로 넣습니다.
   - 같은 과목·제목·출처의 book이 이미 있으면 건너뜁니다(중복 방지).
   - 각 PDF 장을 72 DPI(= 원본 사진 해상도) JPEG로 만들어(`render_jpeg`) 저장소 `data/storage/books/{book_id}/{page_id}.jpg`에 저장합니다.
   - 텍스트는 `…/{page_id}.text.json`에 저장합니다.
   - 그다음 하나의 트랜잭션 안에서 DB에 기록합니다. 기록하는 곳은 `mingyu.books` 1행, `mingyu.processing_runs` 1건, `mingyu.pages` 여러 행이고, 페이지 상태는 EXTRACTED입니다.
   - 중간에 실패하면 DB는 되돌려지고, 저장했던 파일도 지웁니다.
   - 끝나면 `data/reports/team_import/apply_{과목}.json` 리포트를 남깁니다. 216쪽 누락 같은 특이사항도 여기에 적힙니다.

## 직접 확인하는 방법
- **계획 보기(아무것도 바꾸지 않음):**
  ```
  cd backend
  uv run python -m app.ingestion.team_import --dry-run
  ```
  기대 결과:
  - 과목별로 "pages 행 50개 / 64개 / 210개"가 나옵니다.
  - 3과목에 "건너뛰는 PDF 장: 121장", "없는 쪽: 216쪽"이 나옵니다.
  - 마지막 줄들에 "DB 확인 [subjectN]: 이미 있음 → --apply 시 건너뜀"이 나옵니다.
- **쪽번호 대조 이미지 만들기:**
  ```
  uv run python -m app.ingestion.team_import --preview subject3:84,85,120,121,122
  ```
  `data/reports/team_import/preview_subject3.jpg`를 열면 각 장의 아래쪽 쪽번호가 215, 217, 252, 252, 253으로 보입니다.
- **DataGrip에서 볼 것:**
  - `mingyu.books`: 제목이 "2024 ADsP 한 권으로 끝내기 이론편 - N과목 …"인 3행
  - `mingyu.processing_runs`: `pipeline_version = 'team-import-0.1-team-text'`인 3건, 상태는 PARTIAL
  - `mingyu.pages`: `SELECT processing_status, count(*) FROM mingyu.pages GROUP BY 1;` → EXTRACTED 324(이번에 반입한 행 기준)
  - `page_metadata`: 3과목 217쪽 행에는 `missing_before`(216쪽 없음)와 `text.note`(파일명과 내용이 다름)가 있습니다. 1과목 58·59쪽 행의 `text.note`에는 "과1-58-59p.txt의 30번째 줄에서 분할"이 있습니다.
- **다시 넣어도 중복되지 않는지:**
  ```
  uv run python -m app.ingestion.team_import --apply --subject subject1
  ```
  "이미 반입됨 → 건너뜀"이 나와야 합니다.
- **테스트:** 루트에서 `uv run pytest` → 56개 통과

## 아직 안 되는 것
- 반입한 페이지는 텍스트 추출까지만 끝난 상태(EXTRACTED)입니다. 청킹, 임베딩, 시각자료 crop이 아직 없어서 **검색이나 질문에는 아직 쓸 수 없습니다.**
- 3과목 216쪽은 원본 PDF에도 팀 텍스트에도 없어서 빠져 있습니다. 필요하면 교재를 직접 찍어 업로드해야 합니다.
- 반입 페이지를 청킹·임베딩 단계부터 이어서 돌리는 실행 경로가 아직 없습니다(다음 세션 작업).
- 교재 이미지와 텍스트는 `data/`에만 있고 git에는 올라가지 않습니다(저작권). 다른 PC에서는 원본 파일과 page_map.json을 따로 옮겨야 합니다.
