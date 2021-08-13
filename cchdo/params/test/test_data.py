import string

import pytest
import cchdo.params as data
from datetime import date, time

from jsonschema import validate

CF_VERSION = "72"


def test_lengths():
    assert len(data.CFStandardNames) > 1
    assert len(data.WHPNames) > 1


def test_cf_names_self():
    for name in data.CFStandardNames.values():
        assert name.cf is name


cf_name_data = [
    ("sea_water_practical_salinity", "1"),
    ("sea_water_pressure", "dbar"),
    ("moles_of_oxygen_per_unit_mass_in_sea_water", "mol kg-1"),
]


@pytest.mark.parametrize("name,unit", cf_name_data)
def test_a_few_cf_standard_names(name, unit):
    assert name in data.CFStandardNames
    assert isinstance(data.CFStandardNames[name], data.CFStandardName)
    assert data.CFStandardNames[name].canonical_units == unit


cf_alias_data = [
    ("sea_floor_depth", "sea_floor_depth_below_geoid"),
    (
        "moles_per_unit_mass_of_cfc11_in_sea_water",
        "moles_of_cfc11_per_unit_mass_in_sea_water",
    ),
]


@pytest.mark.parametrize("alias,canonical", cf_alias_data)
def test_cf_standard_name_alias(alias, canonical):
    assert alias in data.CFStandardNames
    assert canonical in data.CFStandardNames

    assert data.CFStandardNames[alias] == data.CFStandardNames[canonical]


whp_cf_names = [value for value in data.WHPNames.values() if value.cf_name is not None]


@pytest.mark.parametrize("whpname", whp_cf_names)
def test_whp_cf_names_in_cf_list(whpname):
    assert whpname.cf_name in data.CFStandardNames


whp_error_names = [
    name for name in data.WHPNames.values() if name.error_name is not None
]


@pytest.mark.parametrize("whpname", whp_error_names)
def test_whp_error_names(whpname):
    assert data.WHPNames.error_cols[whpname.error_name] is whpname


whp_unitless_names = [name for name in data.WHPNames.values() if name.whp_unit is None]


@pytest.mark.parametrize("whpname", whp_unitless_names)
def test_whp_no_unit_params(whpname):
    str_name = whpname.whp_name
    tuple_name = (str_name,)

    assert data.WHPNames[str_name] == whpname
    assert data.WHPNames[tuple_name] == whpname


@pytest.mark.parametrize("whpname", whp_cf_names)
def test_whp_cf_property(whpname):
    assert isinstance(whpname.cf, data.CFStandardName)


@pytest.mark.parametrize(
    "whpname", data.WHPNames.values(), ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]"
)
def test_whp_has_nc_name(whpname):
    assert whpname.nc_name is not None


@pytest.mark.parametrize(
    "whpname", data.WHPNames.values(), ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]"
)
def test_whp_name_can_make_nc_attrs(whpname):
    data = whpname.get_nc_attrs()
    assert isinstance(data, dict)


def test_db_dump_matches_files():
    from importlib.resources import path, read_text
    import sqlite3

    db_file = []
    with path("cchdo.params", "params.sqlite3") as p:
        with sqlite3.connect(p) as conn:
            for line in conn.iterdump():
                db_file.append(f"{line}\n")
    db_file = "".join(db_file)
    db_text = read_text("cchdo.params", "params.sqlite3.sql")
    assert db_file == db_text


def test_db_fk_ok():
    from importlib.resources import path
    import sqlite3

    with path("cchdo.params", "params.sqlite3") as p:
        with sqlite3.connect(p) as conn:
            cursor = conn.execute("PRAGMA foreign_key_check;")
            assert len(cursor.fetchall()) == 0


allowed = set(string.ascii_lowercase + string.digits + "_")


@pytest.mark.parametrize(
    "whpname", data.WHPNames.values(), ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]"
)
def test_nc_names_ok(whpname):
    assert set(whpname.nc_name) <= allowed


def test_legacy_json():
    # Validate will raise if this fails
    validate(data.WHPNames.legacy_json, data.WHPNames.legacy_json_schema)
    assert True


def test_whpname_groups():
    groups = data.WHPNames.groups
    assert isinstance(groups, tuple)
    assert hasattr(groups, "cruise")
    assert hasattr(groups, "profile")
    assert hasattr(groups, "sample")


@pytest.mark.parametrize(
    "whpname", data.WHPNames.values(), ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]"
)
def test_nc_attrs(whpname: data.WHPName):
    attrs = whpname.get_nc_attrs()
    assert "whp_name" in attrs

    if whpname.whp_unit is not None:
        assert "whp_unit" in attrs

    if whpname.field_width is not None and whpname.numeric_precision is not None:
        assert "C_format" in attrs

    if whpname.cf_name is None:
        assert "standard_name" not in attrs

    if whpname.error_name is not None:
        err_attrs = whpname.get_nc_attrs(error=True)

        assert err_attrs["whp_name"] == whpname.error_name

        if whpname.cf_name is not None:
            assert whpname.cf_name in err_attrs["standard_name"]
            assert " standard_error" in err_attrs["standard_name"]


@pytest.mark.parametrize(
    "whpname",
    data.WHPNames.values(),
    ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]",
)
def test_strfex_fill(whpname: data.WHPName):
    result = whpname.strfex(float("nan"))
    if whpname.data_type is str:
        assert "nan" == result.strip()
    else:
        assert "-999" == result.strip()

    # castno can never be empty
    if whpname.whp_name != "CASTNO":
        assert len(result) == whpname.field_width


@pytest.mark.parametrize(
    "whpname",
    [whpname for whpname in data.WHPNames.values() if whpname.data_type is float],
    ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]",
)
@pytest.mark.parametrize("value", (10, 10.1))
@pytest.mark.parametrize("override", (None, 15))
def test_strfex_floaty(whpname: data.WHPName, value, override):
    result = whpname.strfex(value, numeric_precision_override=override)

    if whpname.numeric_precision > 0 and override is None:  # type: ignore
        assert "." in result
        assert len(result.split(".")[1]) == whpname.numeric_precision
    elif override is None:
        assert "." not in result

    if override is not None:
        if override > 0:
            assert "." in result
            assert len(result.split(".")[1]) == override
        elif override == 0:
            assert "." not in result


@pytest.mark.parametrize(
    "whpname",
    [whpname for whpname in data.WHPNames.values() if whpname.data_type is str],
    ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]",
)
def test_strfex_special(whpname: data.WHPName):
    result = whpname.strfex(date(2020, 1, 1))
    assert result == "20200101"

    result = whpname.strfex(time(13, 14, 15, 16))
    assert result == "1314"

    result = whpname.strfex("")
    assert result.strip() == "-999"
    assert len(result) == whpname.field_width


@pytest.mark.parametrize(
    "whpname",
    [whpname for whpname in data.WHPNames.values() if whpname.data_type is int],
    ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]",
)
def test_strfex_ints(whpname: data.WHPName):
    result = whpname.strfex(1)
    assert result.strip() == "1"
    assert len(result) == whpname.field_width
    assert "." not in result


@pytest.mark.parametrize(
    "whpname",
    data.WHPNames.values(),
    ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]",
)
@pytest.mark.parametrize("flag", (float("nan"), 2))
def test_strfex_flags(whpname: data.WHPName, flag):
    result = whpname.strfex(flag, flag=True)

    assert result in {"2", "9"}
