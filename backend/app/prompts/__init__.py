"""LLM 프롬프트 파일(UTF-8) 읽기. 문장은 이 폴더의 텍스트 파일에만 두고, 코드는 변수만 채운다.

매 호출마다 파일을 다시 읽으므로 프롬프트를 고치면 서버 재시작 없이 다음 질문부터 반영된다.
자리표시자는 string.Template 형식($name).
"""

import json
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parent


def load_text(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def render(name: str, **values: object) -> str:
    """$name 자리표시자를 채운다. 빠진 값이 있으면 KeyError."""
    return Template(load_text(name)).substitute({k: str(v) for k, v in values.items()})


def load_json(name: str) -> dict:
    return json.loads(load_text(name))
