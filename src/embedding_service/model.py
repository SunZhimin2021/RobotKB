"""bge-m3 ONNX inference wrapper.

bge-m3 supports dense and sparse retrieval in a single model.
- Dense:  last_hidden_state[:, 0, :] (CLS token) → L2-normalized → [N, 1024]
- Sparse: token logits via a linear head → {token_id: weight} per text

ONNX model expects:
    input_ids       int64 [batch, seq_len]
    attention_mask  int64 [batch, seq_len]
    token_type_ids  int64 [batch, seq_len]  (optional depending on export)

Outputs (names vary by export; we resolve at load time):
    last_hidden_state  float32 [batch, seq_len, hidden]
    sparse_logits      float32 [batch, seq_len, vocab]  (if exported with sparse head)
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import onnxruntime as ort
    from tokenizers import Tokenizer

logger = logging.getLogger("robotkb.embedding.model")

# One GPU slot at a time across all async workers
_gpu_semaphore = asyncio.Semaphore(1)


class BgeM3Model:
    def __init__(
        self,
        model_path: Path,
        tokenizer_path: Path,
        execution_provider: str,
        max_token_length: int,
        embedding_dim: int,
    ) -> None:
        self._model_path = model_path
        self._tokenizer_path = tokenizer_path
        self._execution_provider = execution_provider
        self._max_token_length = max_token_length
        self._embedding_dim = embedding_dim

        self._session: ort.InferenceSession | None = None
        self._tokenizer: Tokenizer | None = None
        self._has_sparse_head: bool = False

    def load(self) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        providers = [self._execution_provider]
        if self._execution_provider != "CPUExecutionProvider":
            providers.append("CPUExecutionProvider")

        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self._session = ort.InferenceSession(
            str(self._model_path),
            sess_options=sess_opts,
            providers=providers,
        )

        output_names = {o.name for o in self._session.get_outputs()}
        self._has_sparse_head = "sparse_logits" in output_names

        self._tokenizer = Tokenizer.from_pretrained(str(self._tokenizer_path))
        self._tokenizer.enable_truncation(max_length=self._max_token_length)
        self._tokenizer.enable_padding(pad_token="[PAD]", pad_id=0)

        logger.info(
            "bge-m3 loaded",
            extra={
                "model_path": str(self._model_path),
                "provider": self._execution_provider,
                "sparse_head": self._has_sparse_head,
            },
        )

    def warmup(self) -> None:
        dummy = ["warmup"]
        self._run_dense(dummy)
        logger.info("bge-m3 warmup complete")

    # ------------------------------------------------------------------
    # Public inference API (sync — called from async batcher in thread)
    # ------------------------------------------------------------------

    def embed_dense(self, texts: list[str]) -> list[list[float]]:
        return self._run_dense(texts)

    def embed_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        if not self._has_sparse_head:
            raise RuntimeError(
                "ONNX model was not exported with a sparse head; "
                "use type='dense' or re-export with sparse_logits output."
            )
        return self._run_sparse(texts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tokenize(self, texts: list[str]) -> dict[str, np.ndarray]:
        encodings = self._tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        }

    def _run_dense(self, texts: list[str]) -> list[list[float]]:
        feeds = self._tokenize(texts)
        outputs = self._session.run(["last_hidden_state"], feeds)
        hidden = outputs[0]                    # [N, seq_len, hidden]
        cls_vecs = hidden[:, 0, :]             # [N, hidden]
        # L2 normalize
        norms = np.linalg.norm(cls_vecs, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-12)
        normalized = cls_vecs / norms
        return normalized.tolist()

    def _run_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        feeds = self._tokenize(texts)
        outputs = self._session.run(["last_hidden_state", "sparse_logits"], feeds)
        sparse_logits = outputs[1]             # [N, seq_len, vocab]
        attention_mask = feeds["attention_mask"]
        input_ids = feeds["input_ids"]

        results: list[dict[int, float]] = []
        for i in range(len(texts)):
            token_weights: dict[int, float] = {}
            for pos in range(sparse_logits.shape[1]):
                if attention_mask[i, pos] == 0:
                    continue
                tid = int(input_ids[i, pos])
                weight = float(np.max(sparse_logits[i, pos]))
                if weight > 0:
                    # Keep max weight per token id
                    token_weights[tid] = max(token_weights.get(tid, 0.0), weight)
            results.append(token_weights)
        return results
