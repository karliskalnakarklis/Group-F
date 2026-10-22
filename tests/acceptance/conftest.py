import pytest

import pos

TILL = 1  # register used by most tests (store 1)


@pytest.fixture(scope="session")
def till():
    pos.ensure_open(TILL)
    return TILL
