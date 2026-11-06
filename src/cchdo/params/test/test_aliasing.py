import pytest


def test_add_alias(whpnames):
    whpnames.add_alias("test", "EXPOCODE")

    assert whpnames["test"] == whpnames["EXPOCODE"]
    assert whpnames["test"].whp_alias == "test"


def test_add_alias_fail(whpnames):
    with pytest.raises(KeyError):
        whpnames.add_alias("test", "dummy")


def test_add_alias_depth(whpnames):
    whpnames.add_alias("test", "CTDTMP [ITS-90]_ALT_1")

    assert whpnames["test"] == whpnames["CTDTMP [ITS-90]_ALT_1"]
    assert whpnames["test"].whp_alias == "test"
    assert whpnames["test"].alt_depth == 1


def test_add_alias_depth_odv_style(whpnames):
    whpnames.add_alias("test", "CTDTMP [ITS-90]_ALT_1")

    assert whpnames["test"] == whpnames["CTDTMP [ITS-90]_ALT_1"]
    assert whpnames["test"].whp_alias == "test"
    assert whpnames["test"].alt_depth == 1


def test_add_alias_flag_depth_odv_style(whpnames):
    whpnames.add_alias("test", "CTDTMP [ITS-90]_ALT_1_FLAG_W")

    assert whpnames["test"] == whpnames["CTDTMP [ITS-90]_ALT_1_FLAG_W"]
    assert whpnames["test"].whp_alias == "test"
    assert whpnames["test"].alt_depth == 1
    assert whpnames["test"].flag_col is True


def test_add_alias_flag_depth_odv_style_fail(whpnames):
    with pytest.raises(KeyError):
        whpnames.add_alias("test", "FAKE [ITS-90]_ALT_1_FLAG_W")


def test_add_alias_flag_depth(whpnames):
    whpnames.add_alias("test", "CTDTMP [ITS-90]_ALT_1_FLAG_W")

    assert whpnames["test"] == whpnames["CTDTMP [ITS-90]_ALT_1_FLAG_W"]
    assert whpnames["test"].whp_alias == "test"
    assert whpnames["test"].alt_depth == 1
    assert whpnames["test"].flag_col is True
