from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _fresh_layouts():
    """Each test lays its documents out again (tests that spy on or patch the layout must see it run)."""
    from uniwire.render import _PAGES
    _PAGES.clear()
    yield
