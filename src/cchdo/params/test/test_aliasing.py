import pytest


def test_add_alias(whpnames):
    whpnames.add_alias(("test", None), ("EXPOCODE", None))

    assert whpnames["test"] == whpnames["EXPOCODE"]
    assert whpnames["test"].whp_name_alias == "test"
    assert whpnames["test"].whp_unit_alias is None


def test_add_alias_fail(whpnames):
    with pytest.raises(KeyError):
        whpnames.add_alias(("test", None), ("dummy", None))


def test_add_alias_depth(whpnames):
    whpnames.add_alias(("test", None), ("CTDTMP_ALT_1", "ITS-90"))

    assert whpnames["test"] == whpnames["CTDTMP_ALT_1 [ITS-90]"]
    assert whpnames["test"].whp_name_alias == "test"
    assert whpnames["test"].whp_unit_alias is None
    assert whpnames["test"].alt_depth == 1


def test_add_alias_depth_odv_style(whpnames):
    whpnames.add_alias("test", "CTDTMP_ALT_1 [ITS-90]")

    assert whpnames["test"] == whpnames["CTDTMP_ALT_1 [ITS-90]"]
    assert whpnames["test"].whp_name_alias == "test"
    assert whpnames["test"].whp_unit_alias is None
    assert whpnames["test"].alt_depth == 1


def test_add_alias_flag_depth_odv_style(whpnames):
    whpnames.add_alias("test", "CTDTMP_ALT_1 [ITS-90]_FLAG_W")

    assert whpnames["test"] == whpnames["CTDTMP_ALT_1 [ITS-90]_FLAG_W"]
    assert whpnames["test"].whp_name_alias == "test"
    assert whpnames["test"].whp_unit_alias is None
    assert whpnames["test"].alt_depth == 1
    assert whpnames["test"].flag_col is True


def test_add_alias_flag_depth_odv_style_fail(whpnames):
    with pytest.raises(KeyError):
        whpnames.add_alias("test", "FAKE_ALT_1 [ITS-90]_FLAG_W")


def test_add_alias_flag_depth(whpnames):
    whpnames.add_alias(("test", None), ("CTDTMP_ALT_1_FLAG_W", "ITS-90"))

    assert whpnames["test"] == whpnames["CTDTMP_ALT_1 [ITS-90]_FLAG_W"]
    assert whpnames["test"].whp_name_alias == "test"
    assert whpnames["test"].whp_unit_alias is None
    assert whpnames["test"].alt_depth == 1
    assert whpnames["test"].flag_col is True
