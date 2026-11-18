import sys
from pathlib import Path

# Make tests/gpx_factory.py importable as a plain module.
sys.path.insert(0, str(Path(__file__).parent))

import pytest

from mountain_software import db


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()
