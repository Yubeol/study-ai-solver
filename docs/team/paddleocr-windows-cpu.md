# PaddleOCR을 Windows + CPU에서 돌리기 (검증 완료)

> 상태: **검증 완료**(2026-09-29 설치·실측, 한글 경로 항목은 2026-10-01 재확인).
> 환경: Windows 11, Python 3.12, GPU 없음(CPU 28스레드), 패키지 관리 uv.
> 범위: 인쇄체 한국어 문서 이미지 → 줄 단위 텍스트(+신뢰도, bbox). 손글씨는 다루지 않음.

## 요약
- `paddlepaddle==3.3.1` + `paddleocr==3.7.0`(paddlex 3.7.2가 같이 설치됨)
- 검출 모델은 **mobile**(`PP-OCRv5_mobile_det`), 인식 모델은 **한국어**(`korean_PP-OCRv5_mobile_rec`)를 **둘 다 이름으로 지정**
- `enable_mkldnn=False`(oneDNN 끔)
- 모델 캐시는 import **전에** `PADDLE_PDX_CACHE_HOME` 환경변수로 옮김
- 이미지는 `cv2.imread` 대신 바이트로 읽어 `cv2.imdecode`

## 겪은 문제 4가지와 원인

### 1. 기본 검출 모델(server)로는 A4 한 장이 20분 넘게 끝나지 않음
- 증상: `PaddleOCR(lang="korean")`처럼 언어만 주면 검출 모델로 `PP-OCRv5_server_det`가 올라온다. CPU에서 A4(1654×2339) 한 장이 20분이 지나도 끝나지 않았다.
- 원인: server 검출 모델은 GPU를 전제로 한 큰 모델이라 CPU에서는 너무 느리다.
- 해결: 검출 모델을 `PP-OCRv5_mobile_det`로 지정한다. 같은 이미지가 약 16~17초에 끝났다.

### 2. oneDNN 경로에서 `NotImplementedError`
- 증상: CPU 추론 중
  `NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support [pir::ArrayAttribute<pir::DoubleAttribute>]`
- 원인: paddlepaddle 3.3.x의 CPU oneDNN(mkldnn) 경로 버그(아래 이슈 링크).
- 해결: 공식 파라미터 `enable_mkldnn=False`. 속도는 손해를 본다. Paddle이 고친 버전이 나오면 다시 켜고 속도를 비교한다.

### 3. 검출 모델만 지정하면 인식 모델이 비한국어로 바뀌어 한글이 전부 빠짐
- 증상: 1번 때문에 `text_detection_model_name`만 지정했더니 결과에서 한글이 모두 사라졌다.
- 원인: 모델 이름을 하나라도 주면 PaddleOCR가 `lang` 인자를 무시하고 기본 인식 모델(이때는 `PP-OCRv6_medium_rec`, 비한국어)을 쓴다.
- 해결: 검출을 지정하면 인식도 **반드시** `korean_PP-OCRv5_mobile_rec`로 같이 지정하고 `lang`은 넘기지 않는다. 설정 단계에서 "검출만 있고 인식이 없으면 오류"로 막아 두면 실수를 막을 수 있다.

### 4. 한글이 들어간 경로에서 `cv2.imread`/`cv2.imwrite`가 조용히 실패
- 증상(opencv 4.10.0, Windows에서 재확인): 경로에 한글이 있으면 `cv2.imread`는 경고만 출력하고 `None`을 돌려준다. `cv2.imwrite`는 예외 없이 `False`를 돌려주고 파일을 만들지 않는다. 예외가 나지 않아 한참 뒤에야 문제를 알게 된다.
- 원인: Windows에서 OpenCV의 파일 입출력은 비ASCII(유니코드) 경로를 처리하지 못한다.
- 해결: 파일은 numpy/파이썬으로 바이트를 읽고 쓰고, OpenCV에는 메모리 디코드·인코드만 맡긴다(아래 코드). 업로드처럼 이미 바이트가 있으면 경로를 거치지 않고 바로 `cv2.imdecode`를 쓴다.

## 동작하는 설치 버전
| 패키지 | 버전 | 메모 |
|---|---|---|
| paddlepaddle | 3.3.1 | cp312 win_amd64 wheel 있음(약 105MB), CPU 빌드 |
| paddleocr | 3.7.0 | |
| paddlex | 3.7.2 | paddleocr 의존성으로 설치 |
| opencv-contrib-python | 4.10.0.84 | paddlex가 이 버전으로 고정함. **`opencv-python`을 따로 설치하지 말 것**(cv2 충돌) |

```powershell
uv add "paddlepaddle==3.3.1" "paddleocr==3.7.0" numpy
# pip를 쓰는 환경이면: pip install paddlepaddle==3.3.1 paddleocr==3.7.0
```

## 설정 코드 (독립 예시)
```python
import os
import threading
from pathlib import Path

import cv2
import numpy as np


def create_ocr(model_cache_dir: str | None = None):
    """한국어 인쇄체용 PaddleOCR 엔진. 프로세스당 한 번만 만든다(모델 로딩이 느림)."""
    if model_cache_dir:
        # paddlex가 import될 때 읽으므로 반드시 import 전에 설정한다.
        os.environ["PADDLE_PDX_CACHE_HOME"] = model_cache_dir
    from paddleocr import PaddleOCR

    return PaddleOCR(
        # 모델 이름을 주면 lang은 무시된다. 검출·인식을 둘 다 지정한다(문제 3).
        text_detection_model_name="PP-OCRv5_mobile_det",      # server_det는 CPU에서 너무 느림(문제 1)
        text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
        device="cpu",
        enable_mkldnn=False,                                   # paddlepaddle 3.3.x oneDNN 버그(문제 2)
        # 스캔 문서에는 불필요하고 모델만 늘어나는 단계(기본값은 켜짐)
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def read_image_bgr(path: str | Path) -> np.ndarray:
    """한글 경로에서도 동작하는 이미지 읽기(문제 4)."""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"이미지를 열 수 없음: {path}")
    return image


def write_image(path: str | Path, image: np.ndarray, ext: str = ".png") -> None:
    """한글 경로에서도 동작하는 이미지 저장(문제 4)."""
    ok, buf = cv2.imencode(ext, image)
    if not ok:
        raise ValueError("인코딩 실패")
    buf.tofile(str(path))


_lock = threading.Lock()


def recognize(ocr, image_bgr: np.ndarray) -> list[dict]:
    """줄 단위 결과. 추론 객체의 스레드 안전성이 문서에 없어 잠금으로 한 번에 하나씩 돌린다."""
    with _lock:
        res = ocr.predict(image_bgr)[0]
    return [
        {"text": str(t), "confidence": round(float(s), 4), "bbox": [int(v) for v in b]}  # bbox: x_min, y_min, x_max, y_max
        for t, s, b in zip(res["rec_texts"], res["rec_scores"], res["rec_boxes"])
    ]
```

## 모델 캐시 위치 바꾸기
- 기본 위치는 사용자 홈 아래 `.paddlex`(C: 드라이브)다. 디스크가 부족하면 다른 드라이브로 옮긴다.
- 방법: **paddleocr/paddlex를 import하기 전에** 환경변수 `PADDLE_PDX_CACHE_HOME`에 원하는 폴더를 넣는다(위 `create_ocr`). 모델은 `{그 폴더}/official_models/` 아래에 받아지고, 잠금·임시 파일도 같은 폴더를 쓴다.
- 모델은 Hugging Face에서 `snapshot_download(local_dir=...)`로 받으므로 C:의 HF 캐시에는 참조 파일·로그만 남는다(실측 약 100KB).
- 주의: 같은 프로세스에서 paddlex가 이미 import된 뒤에는 환경변수를 바꿔도 반영되지 않는다. 엔진을 만든 뒤 `paddlex.utils.cache.CACHE_DIR`이 의도한 폴더인지 확인하고 아니면 오류를 내면 C:로 받아지는 사고를 막을 수 있다.
- 영문 경로를 권장한다(한글 경로에서 모델 파일 입출력이 되는지는 확인하지 않았다).
- 공식 사용 문서에는 이 환경변수 설명이 없다. 근거는 PaddleX 소스와 메인테이너 답변이다(아래 출처). 설치된 3.7.2 소스에서도 같은 코드임을 확인했다.
- 모델 2개(mobile 검출 + 한국어 mobile 인식) 캐시 크기: 약 19MB.

## 실측 속도
| 조건 | 결과 |
|---|---|
| 기본 검출(`PP-OCRv5_server_det`), oneDNN 끔 | A4 1장이 20분 넘게 끝나지 않음 → 사용 불가 |
| `PP-OCRv5_mobile_det` + `korean_PP-OCRv5_mobile_rec`, oneDNN 끔 | **1장 약 16~17초**, 30줄 모두 검출, 평균 신뢰도 0.994 |

- 측정 이미지: 맑은 고딕으로 직접 만든 A4(1654×2339) 30줄 문서. CPU 28스레드.
- 첫 호출은 모델 로딩 시간이 더해진다. 엔진은 한 번 만들어 재사용한다.
- **실제 교재 스캔(휴대폰 촬영, 기울기·그림자)으로는 아직 측정하지 않았다.**
- 관찰: 쉼표 뒤 공백이 빠지는 경우가 있다("A, B" → "A,B"). 원문 보존이 필요하면 OCR 결과를 그대로 두고 교정하지 않는다.

## 출처 (확인 2026-09-29)
- 설치: https://pypi.org/project/paddlepaddle/3.3.1/#files , https://pypi.org/project/paddleocr/ , https://www.paddleocr.ai/latest/en/version3.x/installation.html
- 모델 캐시 위치: https://github.com/PaddlePaddle/PaddleX/blob/develop/paddlex/utils/cache.py , https://github.com/PaddlePaddle/PaddleX/blob/develop/paddlex/inference/utils/official_models.py , https://github.com/PaddlePaddle/PaddleOCR/discussions/16631
- oneDNN 오류: https://github.com/PaddlePaddle/Paddle/issues/77340 , https://github.com/PaddlePaddle/Paddle/issues/79749
