FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/models

WORKDIR /app

# CPU-only torch first, so the `embed` extra does not pull the much larger CUDA build (FAP §15).
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml ./
COPY app ./app
RUN pip install ".[embed]"

# Bake the embedding model into the image; production never downloads from Hugging Face.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
ENV HF_HUB_OFFLINE=1

COPY alembic.ini ./

# Milestone 2 corpus, registry and vendored tokenizer. The path is set explicitly because the
# app is pip-installed, so the default (next to app/config.py) depends on which copy is imported.
COPY corpus ./corpus
ENV CORPUS_DIR=/app/corpus

# Railway sets $PORT. Migrations run on every start; keep one replica (EC DB-09). The index is
# rebuilt only when the corpus, chunker settings or model changed; a failed build stops the start,
# so the health check never passes on a broken index (FAP §6.3, §15).
CMD ["sh", "-c", "alembic upgrade head && python -m app.rag.build_index --if-changed && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
