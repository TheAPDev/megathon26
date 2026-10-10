import logging
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.INFO)
os.environ["GG_ENV_FILE"] = os.devnull  # tests never read the developer's .env
os.environ.setdefault("GG_RUNTIME_DIR", tempfile.mkdtemp(prefix="gg-runtime-"))  # tests never touch data/runtime


@pytest.fixture(scope="session")
def value_fn():
    from greenghar.ml.predict import install, value_range
    install()
    return value_range


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from greenghar.api.main import app
    with TestClient(app) as c:
        yield c
