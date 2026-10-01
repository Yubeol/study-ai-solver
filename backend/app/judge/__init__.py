"""판정기(교체 가능 모듈, ARCHITECTURE "판정기", D-007).

지금은 `JUDGE_PROVIDER=none`만 동작한다(판정 생략 → 회색 구간은 답변 + "근거 확신 낮음").
jev_typesafe / jev_cloudflare / llm 구현체는 1-c에서 추가한다.
"""

from typing import Protocol

from app.core.config import Settings


class Judge(Protocol):
    name: str

    def can_answer(self, question: str, evidence: list[str]) -> tuple[bool, float]:
        """(답할 수 있는가, 신뢰도 0~1)."""
        ...


def get_judge(settings: Settings) -> Judge | None:
    if settings.judge_provider == "none":
        return None
    raise NotImplementedError(f"JUDGE_PROVIDER={settings.judge_provider}는 아직 구현되지 않았습니다(none만 가능).")
