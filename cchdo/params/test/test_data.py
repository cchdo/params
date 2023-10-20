import sqlite3
import string
from datetime import date, time
from importlib.resources import as_file, files

import pytest
from jsonschema import validate

import cchdo.params as data

CF_VERSION = "81"


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
    error_inst = data.WHPNames[(whpname.error_name, whpname.whp_unit)]
    assert error_inst == whpname
    assert error_inst.error_col is True
    assert data.WHPNames[data.to_odv((whpname.error_name, whpname.whp_unit))] == whpname


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
    assert whpname.nc_name_flag == f"{whpname.nc_name}_qc"
    assert whpname.nc_name_error == f"{whpname.nc_name}_error"


@pytest.mark.parametrize(
    "whpname", data.WHPNames.values(), ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]"
)
def test_whp_name_can_make_nc_attrs(whpname):
    data = whpname.get_nc_attrs()
    assert isinstance(data, dict)


def test_db_dump_matches_files():
    data = files("cchdo.params")

    db_file = []
    with as_file(data / "params.sqlite3") as p:
        with sqlite3.connect(p) as conn:
            for line in conn.iterdump():
                db_file.append(f"{line}\n")
    db_file = "".join(db_file)
    db_text = (data / "params.sqlite3.sql").read_text()
    for db, text in zip(db_file.splitlines(), db_text.splitlines()):
        assert db == text


def test_db_fk_ok():
    data = files("cchdo.params")

    with as_file(data / "params.sqlite3") as p:
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


@pytest.mark.parametrize(
    "whpname",
    data.WHPNames.values(),
    ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]",
)
def test_odv_param_lookup(whpname: data.WHPName):
    assert data.WHPNames[whpname.odv_key] == whpname


def _unitless(param: data.WHPName):
    return param.whp_unit is None


@pytest.mark.parametrize(
    "whpname",
    filter(_unitless, data.WHPNames.values()),  # type: ignore
    ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]",
)
def test_odv_empty_unit_vatiations(whpname):
    assert data.WHPNames[f"{whpname.whp_name}"] is whpname
    assert data.WHPNames[f"{whpname.whp_name} []"] is whpname
    assert data.WHPNames[f"{whpname.whp_name} [None]"] is whpname
    assert data.WHPNames[f"{whpname.whp_name} [nan]"] is whpname


@pytest.mark.parametrize(
    "whpname",
    data.WHPNames.values(),
    ids=lambda x: f"{x.whp_name}_[{x.whp_unit}]",
)
@pytest.mark.parametrize("depth", [0, 1, 2, 3, 10, 100])
def test_alt_depths(whpname: data.WHPName, depth: int):
    if depth == 0:
        assert data.WHPNames[whpname.odv_key].alt_depth == 0
    else:
        name = f"{whpname.whp_name}_ALT_{depth}"
        assert data.WHPNames[(name, whpname.whp_unit)].alt_depth == depth
