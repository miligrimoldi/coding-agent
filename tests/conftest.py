import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MEMORY_DIR = PROJECT_ROOT / "memory"


@pytest.fixture(autouse=True)
def _cleanup_test_memory_files():
    """
    Los tests que corren Orchestrator.run(workspace_path=".") generan un
    archivo real en memory/ para el workspace "coding-agent" (la raíz del
    repo) -- no es memoria de un proyecto real, así que se borra después
    de cada test para no ensuciar memory/.
    """
    yield

    for path in MEMORY_DIR.glob("coding-agent-*.json"):
        path.unlink()
