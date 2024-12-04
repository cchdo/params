import pytest


def test_add_alias(whpnames):
    whpnames.add_alias(("test", None), ("EXPOCODE", None))

    assert whpnames["test"] == whpnames["EXPOCODE"]
    assert whpnames["test"].whp_name_alias == "test"
    assert whpnames["test"].whp_unit_alias is None


def test_add_alias_fail(whpnames):
    with pytest.raises(KeyError):
        whpnames.add_alias(("test", None), ("dummy", None))
