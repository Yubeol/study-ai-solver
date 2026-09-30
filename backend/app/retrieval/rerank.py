"""리랭커(cross-encoder): 벡터 후보 N개를 질문과 청크를 함께 읽어 다시 점수 매긴다 (ARCHITECTURE "검색 단계 상세").

- 모델은 `RERANKER_MODEL`(비면 리랭크 생략), sentence-transformers `CrossEncoder`로 로드한다.
  캐시는 임베딩과 같은 HF_HOME(`EMBEDDING_MODEL_DIR`).
- 점수는 sigmoid로 0~1(두 후보 모델 카드의 normalize/sigmoid 사용법과 같음). "확인 불가" 2단계 임계값은 이 점수 기준.
- 모델은 프로세스당 1개, 추론은 잠금으로 직렬화한다. 평가에서 모델을 바꿀 때는 release_reranker() 후 다시 로드.
"""

import threading

from app.core.config import Settings

_reranker = None
_reranker_lock = threading.Lock()


class LocalReranker:
    def __init__(self, settings: Settings, model_name: str | None = None):
        name = model_name or settings.reranker_model
        if not name:
            raise RuntimeError("RERANKER_MODEL이 비어 있습니다.")
        from app.ingestion.embedding import ensure_hf_home

        ensure_hf_home(settings)
        import torch
        from sentence_transformers import CrossEncoder

        self.model_name = name
        self._model = CrossEncoder(
            name,
            device=settings.reranker_device,
            max_length=settings.reranker_max_length,
            activation_fn=torch.nn.Sigmoid(),
        )
        self._batch_size = settings.reranker_batch_size
        self._lock = threading.Lock()

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        with self._lock:
            scores = self._model.predict(
                [(query, t) for t in texts], batch_size=self._batch_size, show_progress_bar=False
            )
        return [float(s) for s in scores]

    def count_tokens(self, query: str, text: str) -> int:
        """질문+청크 쌍의 토큰 수(잘림 전). max_length를 넘는지 확인용."""
        return len(self._model.tokenizer(query, text, truncation=False)["input_ids"])


def get_reranker(settings: Settings, model_name: str | None = None) -> LocalReranker:
    """처음 호출할 때 로드하고 이후 같은 객체를 돌려준다. 다른 모델을 요청하면 기존 모델을 내리고 새로 로드."""
    global _reranker
    name = model_name or settings.reranker_model
    with _reranker_lock:
        if _reranker is None or _reranker.model_name != name:
            _reranker = None
            _gc()
            _reranker = LocalReranker(settings, name)
        return _reranker


def release_reranker() -> None:
    global _reranker
    with _reranker_lock:
        _reranker = None
    _gc()


def _gc() -> None:
    import gc

    gc.collect()


def rerank(query: str, rows: list[dict], reranker, input_field: str) -> list[dict]:
    """벡터 후보(점수 내림차순)를 리랭커 점수 내림차순으로 다시 정렬한다.

    각 행에 vector_rank(1부터)·vector_score(원래 score)·rerank_score를 붙이고, score는 rerank_score로 바꾼다.
    """
    scores = reranker.score(query, [r[input_field] or "" for r in rows])
    out = [
        {**r, "vector_rank": i, "vector_score": r["score"], "rerank_score": s, "score": s}
        for i, (r, s) in enumerate(zip(rows, scores, strict=True), 1)
    ]
    out.sort(key=lambda r: (-r["rerank_score"], r["vector_rank"]))
    return out
