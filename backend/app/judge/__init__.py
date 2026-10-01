"""판정기(교체 가능 모듈, ARCHITECTURE "판정기", D-007, D-028).

- `JUDGE_PROVIDER=none`: 판정 생략 → 회색 구간은 답변 + "근거 확신 낮음".
- `jev_typesafe`: TypeSafe 직접 API(app/judge/jev.py). 회색 구간에서만 can_answer를 부른다.
- jev_cloudflare / llm 구현체는 아직 없다.
"""

from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import Settings


@dataclass
class JudgeResult:
    """can_answer 결과. 오류면 probability=None, error에 이유(호출 측은 none과 같은 동작)."""
    probability: float | None  # "답할 수 있다"일 확률 0~1
    model: str | None = None  # 실제로 응답한 모델(예: jev-1.13.0)
    usage: dict | None = None  # 입력·출력 토큰
    attempts: list[dict] = field(default_factory=list)  # 실패한 시도(시도 번호, 오류)
    error: str | None = None


class Judge(Protocol):
    name: str

    def can_answer(self, question: str, evidence: list[dict]) -> JudgeResult:
        """evidence: 근거 K개(n, page, path, clean_text)."""
        ...

    def close(self) -> None: ...


def get_judge(settings: Settings) -> Judge | None:
    if settings.judge_provider == "none":
        return None
    if settings.judge_provider == "jev_typesafe":
        from app.judge.jev import JevJudge

        return JevJudge(settings)
    raise NotImplementedError(f"JUDGE_PROVIDER={settings.judge_provider}는 아직 구현되지 않았습니다(none, jev_typesafe만 가능).")
