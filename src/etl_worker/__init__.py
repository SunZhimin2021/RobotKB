"""etl_worker — Document processing pipeline for RobotKB.

Public API:
    ETLPipeline  — main pipeline class (parse → NER → chunk → embed → store)
    TextChunker  — generic paragraph chunker
    SectionChunker — section-boundary chunker (datasheet mode)
    CodeChunker  — code-block boundary chunker
    FaultChunker — fault-case triple chunker
    NERVerifier  — chip/board entity verifier
    get_chunker  — factory: returns appropriate chunker for a DocumentCategory
"""

from etl_worker.chunkers import (
    CodeChunker,
    FaultChunker,
    SectionChunker,
    TextChunker,
    get_chunker,
)
from etl_worker.ner import NERVerifier
from etl_worker.pipeline import ETLPipeline

__all__ = [
    "ETLPipeline",
    "TextChunker",
    "SectionChunker",
    "CodeChunker",
    "FaultChunker",
    "NERVerifier",
    "get_chunker",
]
