import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # push/
sys.path.insert(0, str(Path(__file__).resolve().parent))          # push/tests/

from fixture import make_db  # noqa: E402


@pytest.fixture
def con(tmp_path):
    c = make_db(tmp_path / "t.db")
    yield c
    c.close()
