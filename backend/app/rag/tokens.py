"""Token counting with the embedder's own tokenizer (FAP §5.1, adjustment A4).

The tokenizer file is vendored under `corpus/tokenizer/`, so chunk sizes are measured
offline and identically in CI, locally and in production, without installing torch.
Counts include the special tokens ([CLS], [SEP]) the embedder adds, because those count
towards its 512-token input limit too.
"""

from functools import lru_cache
from pathlib import Path

from tokenizers import Tokenizer

from app.config import get_settings

TOKENIZER_SUBPATH = Path("tokenizer") / "bge-small-en-v1.5" / "tokenizer.json"


@lru_cache
def get_tokenizer(path: str | None = None) -> Tokenizer:
    path = path or str(Path(get_settings().CORPUS_DIR) / TOKENIZER_SUBPATH)
    tokenizer = Tokenizer.from_file(path)
    tokenizer.no_truncation()  # we measure the real length; never cut silently
    tokenizer.no_padding()
    return tokenizer


def count_tokens(text: str) -> int:
    return len(get_tokenizer().encode(text, add_special_tokens=True).ids)
