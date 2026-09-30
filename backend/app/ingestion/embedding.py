"""로컬 임베딩 (BGE-M3, sentence-transformers, D-009 / D-020).

- 모델 캐시는 `EMBEDDING_MODEL_DIR` → `HF_HOME`. huggingface_hub는 import 시점에 환경변수를 읽으므로
  sentence_transformers는 이 모듈 안에서만, 환경변수를 설정한 뒤 지연 import한다.
  이미 다른 위치로 import돼 있으면(모델이 C:에 받아지므로) 오류로 멈춘다.
- 모델은 프로세스당 1개(로딩이 느림), 추론은 잠금으로 직렬화한다.
- 벡터는 L2 정규화해서 저장한다(검색은 cosine, `<=>`).
"""

import os
import threading
from pathlib import Path

import numpy as np

from app.core.config import Settings

_embedder = None
_embedder_lock = threading.Lock()


def ensure_hf_home(settings: Settings) -> None:
    """HF_HOME을 EMBEDDING_MODEL_DIR로 맞춘다(임베딩·리랭커 공용 캐시). sentence_transformers import 전에 부른다.

    이미 다른 위치로 import돼 있으면 모델이 C:에 받아지므로 오류로 멈춘다.
    """
    if settings.embedding_model_dir is None:
        return
    os.environ["HF_HOME"] = str(settings.embedding_model_dir)
    import huggingface_hub.constants

    actual = Path(huggingface_hub.constants.HF_HOME).resolve()
    if actual != settings.embedding_model_dir.resolve():
        raise RuntimeError(f"HF_HOME이 설정과 다름(이미 import됨): {actual}")


class LocalEmbedder:
    def __init__(self, settings: Settings):
        if not settings.embedding_model:
            raise RuntimeError("EMBEDDING_MODEL이 비어 있습니다.")
        ensure_hf_home(settings)
        from sentence_transformers import SentenceTransformer

        self.model_name = settings.embedding_model
        self._model = SentenceTransformer(settings.embedding_model, device=settings.embedding_device)
        self._model.max_seq_length = settings.embedding_max_seq_length
        self._batch_size = settings.embedding_batch_size
        self.dim = self._model.get_embedding_dimension()
        if self.dim != settings.embedding_dim:
            raise RuntimeError(f"임베딩 차원 불일치: 모델 {self.dim}, 설정 {settings.embedding_dim}")
        self._lock = threading.Lock()

    def encode(self, texts: list[str]) -> np.ndarray:
        """(len(texts), dim) float32, 각 행은 L2 정규화."""
        with self._lock:
            vecs = self._model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return np.asarray(vecs, dtype=np.float32)


def get_embedder(settings: Settings) -> LocalEmbedder:
    """처음 호출할 때 모델을 로드하고, 이후에는 같은 객체를 돌려준다."""
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                _embedder = LocalEmbedder(settings)
    return _embedder


def release_embedder() -> None:
    """모델을 메모리에서 내린다(평가에서 질문 임베딩 후 리랭커를 올리기 전에, RAM 절약)."""
    global _embedder
    with _embedder_lock:
        _embedder = None
    import gc

    gc.collect()


def to_pgvector(vec: np.ndarray) -> str:
    """pgvector 텍스트 형식 "[0.1,0.2,…]"(쿼리에서 ::public.vector로 캐스팅)."""
    return "[" + ",".join(f"{float(x):.7g}" for x in vec) + "]"
