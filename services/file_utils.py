"""Utility per operazioni su file."""

import hashlib
from pathlib import Path


def hash_file(path: Path, chunk_size: int = 1_048_576) -> str:
    """Calcola SHA-256 del file leggendo a chunk."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
