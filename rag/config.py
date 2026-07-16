import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DOCUMENTS_DIR = PROJECT_ROOT / "knowledge_base" / "raw"
CHROMA_DIRECTORY = PROJECT_ROOT / "knowledge_base" / "chroma"

COLLECTION_NAME = os.environ.get(
    "RAG_COLLECTION",
    "technical_docs",
)

EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL",
    "text-embedding-3-small",
)

DEFAULT_TOP_K = int(
    os.environ.get("RAG_TOP_K", "5")
)

MIN_SIMILARITY = float(
    os.environ.get("RAG_MIN_SIMILARITY", "0.45")
)