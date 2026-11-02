"""Global pytest configuration, fixtures, and marker management."""

import pytest

from app.api import set_llm_client
from app.llm import FakeLLMClient, OllamaClient


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: marks tests requiring a running live Ollama service (skipped by default)"
    )


def pytest_collection_modifyitems(config, items):
    # Skip live tests by default unless explicitly invoked with -m live
    markexpr = config.getoption("markexpr", default="")
    if "live" not in markexpr:
        skip_live = pytest.mark.skip(reason="Live test requires running Ollama service. Run with: pytest -m live")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def default_fake_llm(request):
    """Automatically inject FakeLLMClient for all unit tests unless marked @pytest.mark.live."""
    if "live" in request.keywords:
        set_llm_client(OllamaClient())
        yield
        set_llm_client(None)
    else:
        set_llm_client(FakeLLMClient())
        yield
        set_llm_client(None)
