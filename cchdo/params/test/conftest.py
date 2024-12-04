import pytest

from cchdo.params import default_whp_names


@pytest.fixture
def whpnames():
    return default_whp_names()
