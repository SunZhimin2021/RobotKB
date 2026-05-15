"""bge-reranker-v2-m3 ONNX inference wrapper.

The reranker takes (query, passage) pairs and outputs a relevance score per pair.

ONNX model expects:
    input_ids       int64 [batch, seq_len]   — "[CLS] query [SEP] passage [SEP]"
    attention_mask  int64 [batch, seq_len]
    token_type_ids  int64 [batch, seq_len]

Output:
    logits          float32 [batch, 1] or [batch]  — raw relevance score
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger("robotkb.reranker.model")

# Shared with embedding service — only one GPU job at a time
from embedding_service.model import _gpu_semaphore  # noqa: F401  (re-exported)


class BgeRerankerModel:
    def __init__(
        self,
        model_path: Path,
        tokenizer_path: Path,
        execution_provider: str,
        max_token_length: int,
    ) -> None:
        self._model_path = model_path
        self._tokenizer_path = tokenizer_path
        self._execution_provider = execution_provider
        self._max_token_length = max_token_length

        self._session = None
        self._tokenizer = None

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

        self._tokenizer = Tokenizer.from_pretrained(str(self._tokenizer_path))
        self._tokenizer.enable_truncation(max_length=self._max_token_length)
        self._tokenizer.enable_padding(pad_token="[PAD]", pad_id=0)

        logger.info(
            "bge-reranker-v2-m3 loaded",
            extra={
                "model_path": str(self._model_path),
                "provider": self._execution_provider,
            },
        )

    def warmup(self) -> None:
        self.rerank("warmup query", ["warmup passage"])
        logger.info("bge-reranker warmup complete")

    def rerank(self, query: str, passages: list[str]) -> list[float]:
        """Return raw relevance scores, one per passage (same order as input)."""
        pairs = [f"{query} [SEP] {p}" for p in passages]
        encodings = self._tokenizer.encode_batch(pairs)

        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

        outputs = self._session.run(
            ["logits"],
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )
        logits = outputs[0]  # [N, 1] or [N]
        scores = logits.squeeze(-1).tolist()
        if isinstance(scores, float):
            scores = [scores]
        return scores
