"""
TEWL test fixtures.

Provides stateless fixtures for testing the TEWL script using query script run.
"""

import pytest
from pathlib import Path


TEWL_SCRIPT_PATH = Path(__file__).parent.parent.parent / "tewl" / "script.py"


@pytest.fixture(scope="session")
def tewl_script_code():
    """Returns the TEWL script source code."""
    return TEWL_SCRIPT_PATH.read_text()
