# 페이지를 넘어 이어지는 R 코드 처리 (초안)

> 상태: **설계 단계, 아직 검증 전**(2026-10-01). 실제 교재 데이터에는 아직 적용하지 않았다.
> 아래 코드는 원리를 보여 주는 **독립 함수 예시**다. 직접 만든 예시 줄로만 자체 검사를 통과했고, 실제 교재로는 검증하지 않았다.
> 예시 줄은 교재 원문이 아니라 비슷한 모양으로 새로 만든 것이다.

## 1. 문제: 무엇이 왜 깨지나
- 많은 RAG 적재 파이프라인은 **페이지 단위로 청킹**한다(청크가 페이지를 넘지 않게). 출처를 "몇 쪽"으로 정확히 보여 주고 페이지 하나만 다시 처리할 수 있어서 편하기 때문이다.
- 그런데 교재의 R 코드 예제는 페이지 끝에서 잘려 다음 페이지로 이어지는 경우가 많다. 그러면 하나의 예제가 두 청크로 갈린다.
  - 앞 청크: 설명 + 코드 앞부분(`> x <- …`, `> mean(x)`)
  - 뒤 청크: 실행 결과 조각(`[1] 81.66667`)이나 코드 뒷부분
- 뒤 청크가 짧고 한글이 거의 없으면 "그림 글자·잡음 조각" 필터(예: 짧고 한글 비율이 낮으면 검수 대기로 돌리고 검색에서 제외)에 걸려 **검색에서 사라진다**.
- 결과적으로 "아래 R 코드의 출력 결과는?" 같은 시험형 질문에서 코드와 결과를 함께 근거로 보여 줄 수 없다. 코드만 있거나 결과만 있는 근거는 답변 근거로 약하다.

## 2. 조사 결과 (우리 교재, 2026-10-01, DB 읽기만)
기준: 페이지 본문(머리말·쪽번호·꼬리말 제외)의 마지막 줄과 다음 페이지 첫 본문 줄을 비교했다. 아래 코드 줄 판단 규칙의 초기 버전을 썼다.

| 기준 | 1과목 | 2과목 | 3과목(R 포함) |
|---|---|---|---|
| 엄격: 앞 페이지 마지막 줄과 다음 페이지 첫 줄이 모두 코드, 다음 첫 줄이 제목 아님 | 0 | 0 | 9건 |
| 완화: 앞뒤 3줄 안에 코드, `#` 주석의 한글 무시, 열 이름 줄 포함 | 0 | 1(도식, 오검출) | 40건 |

- 엄격 기준 9건 중 실제 코드 이어짐은 6건(134→135, 149→150, 206→207, 222→223, 280→281, 295→296쪽)이고, 3건은 그래프 축 글자를 코드로 잘못 잡은 것이다(272→273, 303→304, 337→338쪽).
- 완화 기준 40건을 눈으로 분류한 잠정 결과: 코드·출력 이어짐 약 18건, 앞 예제가 끝나고 다음 예제가 시작하는 경우 4건, 그래프·수식 글자 오검출 19건.
- **뒷부분 첫 청크가 검색에서 빠진 것(검수 대기)은 3건**(135, 142, 143쪽, 모두 "R 기초" 단원)이다. 엄격 기준으로는 135쪽만 잡혔다. 나머지 두 곳은 숫자 없는 열 이름 줄, 페이지 끝 OCR 조각(글자 1개), 한글 주석이 붙은 코드 줄 때문에 놓쳤다.
- 교훈: 교재 텍스트에는 그래프 축 눈금·수식 조각이 숫자·기호 줄로 섞여 있다. 그래서 **"숫자·기호 줄 = 출력"만으로는 코드와 구별되지 않는다.**

## 3. 해결 방향

### 3-1. 코드 줄 인식 규칙
- 코드 줄: 아래 중 하나에 해당하고, `#` 앞(코드 부분)의 한글 비율이 낮은 줄
  - 프롬프트 `>`로 시작 / 이어짐 `+ `로 시작 / 대입 `<-` / 함수 호출 `이름(`(`library(`, `summary(` 등)
- 출력 줄: `[1]`·`[,1]`로 시작, `##`로 시작, 한글 없는 숫자·기호 줄(요약 표, 계수 표), 데이터프레임 열 이름 줄
- **출력 줄은 앞에 코드 줄이 있는 블록 안에서만 출력으로 인정**한다(그래프 숫자 오검출 방지).
- 코드 블록 = 연속된 코드·출력 줄 묶음. 코드 바로 앞의 설명 문장(1~2줄)과 "예제N" 표시는 블록의 머리로 같이 잡는다.

### 3-2. 페이지 넘김 이어짐 판단
다음 세 조건을 모두 만족하면 이어진 것으로 본다.
1. 앞 페이지의 마지막 본문 줄이 코드 블록 안에 있다.
2. 다음 페이지의 첫 본문 줄이 코드 또는 출력 줄이다.
3. 그 사이에 새 제목(장·절·항·■ 박스 등)이 없다. 다음 페이지가 "예제N"이나 기출 문제 블록으로 시작하면 새 블록으로 보고 이어짐이 아니다.

판단할 때 글자 1~2개짜리 OCR 조각 줄은 건너뛴다.

### 3-3. 합치는 방법
- **이어진 코드 블록만** 예외로 페이지를 넘긴다. 앞 페이지의 마지막 코드 블록과 다음 페이지 앞쪽의 이어지는 코드·출력 줄을 **한 청크**로 만든다.
- 다음 페이지의 나머지 본문은 평소대로 그 페이지의 청크가 된다. 일반 본문은 계속 페이지를 넘지 않는다.
- 청크의 대표 페이지(`page_id`)는 **시작 페이지**로 한다. 전체 페이지와 줄 범위는 청크 메타데이터에 남긴다. 예: `spans: [{page, line_range}, {page, line_range}]`. 테이블에 JSON 메타데이터 칸이 있으면 컬럼을 추가하지 않아도 된다.
- 다음 페이지에는 "앞 페이지 청크가 몇 번째 줄까지 가져갔는지"를 기록한다.
- 한 페이지만 다시 청킹할 때는 이어진 앞·뒤 페이지를 **함께** 다시 처리해야 한다. 그렇지 않으면 줄이 중복되거나 빠진다.
- **코드와 실행 결과는 같은 청크**에 둔다. 길이 상한으로 나눌 때도 코드+출력 쌍의 경계에서 자른다. 출력만 떨어진 조각은 만들지 않고, 그래도 생기면 앞 청크에 합친다.

### 3-4. 출처를 페이지 범위로 표시
- 답변 근거·검색 결과에서 "226~227쪽"처럼 범위로 보여 준다(`spans`에서 계산).
- 검색 평가에서 "정답 쪽"을 판정할 때도 `spans`의 모든 쪽을 정답 후보로 본다.

### 3-5. 임베딩 텍스트 구성
- 코드 청크의 임베딩 입력 = **제목 경로 + 코드 앞 설명 문장 + 코드(출력 포함)**
- 코드만으로는 의미 검색이 약하다. 설명 문장이 없거나 짧아 검색이 잘 안 되면(평가로 확인) LLM으로 "이 코드가 하는 일" 한두 문장을 만들어 **임베딩 입력에만** 추가한다. 원문 필드에는 넣지 않고, 생성문이라는 표시를 남긴다.

### 3-6. 시각자료 crop일 때: 세로로 이어 붙이기
- 페이지를 넘는 코드·표를 이미지로 잘라 보여 줄 때는 앞 페이지 아래쪽 crop과 다음 페이지 위쪽 crop을 **세로로 이어 붙여 하나의 이미지**로 만든다. 너비는 넓은 쪽에 맞추고 빈 곳은 흰색으로 채운다.
- 이미지 메타데이터에도 시작 페이지와 전체 페이지 범위를 기록한다.
- 이어짐 판단은 3-2와 같은 규칙을 쓴다.

## 4. 독립 함수 예시
의존성은 `re`, `numpy`뿐이다. 입력은 "머리말·쪽번호를 이미 뺀 본문 줄 목록"이라고 가정한다.

```python
import re

import numpy as np

_HANGUL = re.compile(r"[가-힣]")
_CODE_SIGNS = (
    re.compile(r"^>\s?\S"),                 # 프롬프트: > summary(x)
    re.compile(r"^\+\s"),                   # 이어지는 줄: + 0.5)
    re.compile(r"<-"),                      # 대입: x <- c(1, 2)
    re.compile(r"\b[A-Za-z_][\w.]*\("),     # 함수 호출: library(, mean(
)
_OUTPUT_SIGNS = (
    re.compile(r"^\[\d*,?\d*\]"),           # [1] 3 / [,1]
    re.compile(r"^##"),                     # ## 출력
    re.compile(r"^[\w.\-+*:=~$%()\[\],'\"/<>| ]+$"),  # 한글 없는 숫자·기호 줄(표 형태 출력)
)
_HEADING = re.compile(r"^(\d{1,2}장$|0\d\s*\S|\d{1,2}[.)]\s*[가-힣A-Za-z(]|■)")
_NEW_BLOCK = ("예제", "기출유형")


def hangul_ratio(s: str) -> float:
    return len(_HANGUL.findall(s)) / len(s) if s else 0.0


def line_kind(line: str) -> str | None:
    """'code' / 'output' / None. 주석(# 뒤)의 한글은 비율 계산에서 뺀다."""
    s = line.strip()
    if not s:
        return None
    code_part = s.split("#", 1)[0].strip() or s
    if hangul_ratio(code_part) >= 0.2:
        return None
    if any(p.search(s) for p in _CODE_SIGNS):
        return "code"
    if hangul_ratio(s) == 0 and any(p.search(s) for p in _OUTPUT_SIGNS):
        return "output"
    return None


def code_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """연속된 코드·출력 줄 묶음의 (시작, 끝) 줄 번호(끝 포함).
    출력 줄은 앞에 코드 줄이 있는 블록 안에서만 인정한다(그래프 축 눈금 같은 숫자 줄 오검출 방지)."""
    blocks, start, has_code = [], None, False
    for i, line in enumerate(lines):
        kind = line_kind(line)
        if kind == "code" or (kind == "output" and has_code):
            if start is None:
                start = i
            has_code = has_code or kind == "code"
        else:
            if start is not None and has_code:
                blocks.append((start, i - 1))
            start, has_code = None, False
    if start is not None and has_code:
        blocks.append((start, len(lines) - 1))
    return blocks


def continues_to_next_page(prev_body: list[str], next_body: list[str]) -> bool:
    """앞 페이지 마지막 본문 줄이 코드 블록 안이고, 다음 페이지 첫 본문 줄이 코드·출력이며, 사이에 제목이 없는가.
    두 목록은 머리말·쪽번호·꼬리말을 뺀 본문 줄. 글자 1~2개짜리 OCR 조각은 건너뛴다."""
    prev = [l for l in prev_body if len(l.strip()) > 2]
    nxt = [l for l in next_body if len(l.strip()) > 2]
    if not prev or not nxt:
        return False
    blocks = code_blocks(prev)
    if not blocks or blocks[-1][1] != len(prev) - 1:
        return False                        # 앞 페이지가 코드로 끝나지 않음
    first = nxt[0].strip()
    if _HEADING.match(first) or first.startswith(_NEW_BLOCK):
        return False                        # 새 제목·새 예제로 시작하면 이어짐 아님
    return line_kind(first) is not None


def page_range_label(pages: list[str]) -> str:
    """출처 표시: ['226'] → '226쪽', ['226', '227'] → '226~227쪽'."""
    return f"{pages[0]}쪽" if len(pages) == 1 else f"{pages[0]}~{pages[-1]}쪽"


def merge_continued_block(prev_page: dict, next_page: dict) -> dict:
    """앞 페이지의 마지막 코드 블록 + 다음 페이지 앞쪽의 이어지는 코드·출력 줄을 한 청크로 합친다.
    page는 {"page_id", "printed_page", "lines"(본문 줄)}. 반환값의 page_id는 시작 페이지,
    spans에는 두 페이지의 줄 범위를 남긴다(다음 페이지는 next_start줄부터 평소대로 청킹)."""
    start, end = code_blocks(prev_page["lines"])[-1]
    n = 0
    while n < len(next_page["lines"]) and line_kind(next_page["lines"][n]) is not None:
        n += 1
    text_lines = prev_page["lines"][start : end + 1] + next_page["lines"][:n]
    return {
        "page_id": prev_page["page_id"],
        "text": "\n".join(l.strip() for l in text_lines),
        "spans": [
            {"page_id": prev_page["page_id"], "printed_page": prev_page["printed_page"], "line_range": [start, end]},
            {"page_id": next_page["page_id"], "printed_page": next_page["printed_page"], "line_range": [0, n - 1]},
        ],
        "source_label": page_range_label([prev_page["printed_page"], next_page["printed_page"]]),
        "next_start": n,
    }


def build_embedding_text(heading_path: list[str], intro: str, code: str, generated_note: str = "") -> str:
    """코드 청크의 임베딩 입력 = 제목 경로 + 코드 앞 설명 문장 + 코드(출력 포함).
    generated_note(LLM이 만든 '이 코드가 하는 일')는 설명이 부족할 때만, 임베딩 입력에만 넣는다."""
    parts = [" > ".join(heading_path), intro.strip(), generated_note.strip(), code.strip()]
    return "\n\n".join(p for p in parts if p)


def stack_crops_vertically(top: np.ndarray, bottom: np.ndarray, gap: int = 8,
                           fill: int = 255) -> np.ndarray:
    """앞 페이지 아래쪽 crop과 다음 페이지 위쪽 crop을 세로로 이어 붙인다(BGR, 너비는 넓은 쪽에 맞춰 오른쪽을 흰색으로 채움)."""
    width = max(top.shape[1], bottom.shape[1])

    def pad(img: np.ndarray) -> np.ndarray:
        out = np.full((img.shape[0], width, 3), fill, dtype=img.dtype)
        out[:, : img.shape[1]] = img
        return out

    spacer = np.full((gap, width, 3), fill, dtype=top.dtype)
    return np.vstack([pad(top), spacer, pad(bottom)])
```

예시 입력(직접 만든 줄, 교재 원문 아님)과 기대 결과:
```python
page_a = ["3) 벡터 만들기", "• c() 함수로 벡터를 만들고 평균을 구해 보자.",
          "> scores <- c(70, 85, 90)", "> mean(scores)"]
page_b = ["[1] 81.66667", "> length(scores)", "[1] 3", "• length()는 원소 개수를 돌려준다."]

continues_to_next_page(page_a, page_b)                      # True
continues_to_next_page(page_a, ["4) 행렬", "• matrix() …"])   # False (제목으로 시작)
code_blocks(["0.0 0.2 0.4 0.6", "1.0 2.0 3.0"])             # [] (코드 없는 숫자 줄은 출력으로 보지 않음)
m = merge_continued_block({"page_id": "p1", "printed_page": "41", "lines": page_a},
                          {"page_id": "p2", "printed_page": "42", "lines": page_b})
m["source_label"], m["next_start"]                          # ('41~42쪽', 3)
build_embedding_text(["R 기초", "3) 벡터 만들기"], page_a[1], m["text"])
# 'R 기초 > 3) 벡터 만들기\n\n• c() 함수로 벡터를 만들고 평균을 구해 보자.\n\n> scores <- c(70, 85, 90)\n> mean(scores)\n[1] 81.66667\n> length(scores)\n[1] 3'
```

알려진 한계(예시 코드 기준):
- 제목 판별(`_HEADING`)은 우리 교재의 번호 형식("1장", "01 절", "1. 항", "1) 세부", "■")에 맞춘 것이다. 다른 교재는 제목 규칙을 바꿔야 한다.
- 영문 설명 문장 한 줄(예: 그래프 축 이름)은 출력 줄로 잡힐 수 있다. 코드 줄이 앞에 있어야 출력으로 인정하므로 오검출은 줄지만 0은 아니다.

## 5. 구현 후 채울 칸
### 5-1. 실제 코드
- (구현 후) 적용한 파일·함수 위치, 위 예시와 달라진 점

### 5-2. 적용 전후 비교
| 항목 | 적용 전 | 적용 후 |
|---|---|---|
| 페이지를 넘어 합쳐진 코드 청크 수 | 0 | |
| 코드 이어짐 오검출(그래프·수식 글자가 코드로 묶임) | — | |
| 검색 제외(검수 대기) 코드 조각 청크 | 3 (135, 142, 143쪽) | |
| 전체 검수 대기 청크 | 11 | |
| R 코드 질문 검색 결과(정답 순위, 리랭커 점수) | | |
| 기존 평가 세트 hit@1 / MRR | 22/26 / 0.917 | |

- 비교에 쓴 질문과 메모: (구현 후)
