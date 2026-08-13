#!/usr/bin/env python3
"""Download and cache the embedding model used by the prioritization agent."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings
from reports.prioritize import _compute_embeddings


def main() -> None:
    print(f"Precalentando modelo: {settings.prioritize_embedding_model}")
    _compute_embeddings(["editorial news warmup"])
    print("Modelo listo.")


if __name__ == "__main__":
    main()
