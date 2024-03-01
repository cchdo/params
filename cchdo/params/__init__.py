from collections import UserDict
from dataclasses import asdict
from functools import cached_property
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from json import loads
from typing import NamedTuple

from ._cf_names import cf_standard_names as _cf_standard_names
from ._whp_names import _aliases
from ._whp_names import whp_names as _whp_names
from .core import CFStandardName, WHPName

__all__ = ["CFStandardNames", "WHPNames"]

try:
    __version__ = version("cchdo.params")
except PackageNotFoundError:
    __version__ = "999"

WHPNameKey = str | tuple[str, str | None]


def to_odv(key: tuple[str, str | None]):
    """Transform a (param, unit) tuple into the correct ODV style PARAM [UNIT] string

    Does not check if the param exists

    >>> to_odv(("EXPOCODE", None))
    'EXPOCODE'
    >>> to_odv(("CTDPRS", "DBAR"))
    'CTDPRS [DBAR]'
    """
    name, unit = key
    if unit is None:
        return name
    return f"{name} [{unit}]"


class WHPNameGroups(NamedTuple):
    cruise: frozenset[WHPName]
    profile: frozenset[WHPName]
    sample: frozenset[WHPName]


def normalize_odv_name(name: str, return_parts=False):
    unit: str | None = None
    if not ("[" in name or "]" in name):
        if return_parts:
            return name, unit

        return name.strip()

    if name.count("[") != name.count("]"):
        raise ValueError("Unbalanced unit brackets")
    units_start = name.find("[")
    units_end = name.rfind("]")

    param = name[:units_start].strip()
    unit = name[units_start + 1 : units_end].strip()
    if isinstance(unit, str) and unit.lower() in {"", "none", "nan"}:
        unit = None

    if return_parts:
        return param, unit

    if unit is None:
        return param
    else:
        return f"{param} [{unit}]"


def alt_depth(name: str) -> tuple[str, int]:
    if "_ALT_" not in name:
        return name, 0
    _name, _depth = name.split("_ALT_", maxsplit=1)
    try:
        depth = int(_depth)
    except ValueError as err:
        raise ValueError("could not parse alternate number") from err

    return _name, depth


def flag_name(name: str) -> tuple[str, bool]:
    if name.endswith("_FLAG_W"):
        return name.removesuffix("_FLAG_W"), True
    return name, False


class _WHPNames(dict[WHPNameKey, WHPName]):
    """A Mapping (i.e. dict) providing a lookup between a WOCE style param and unit to an instance of :class:`WHPName`

    .. warning::
      This class should not be directly used, instead use the premade :data:`WHPNames` instance from this module

    Parameters are looked up using a tuple of `(name, unit)`.

    >>> WHPNames[("CTDPRS", "DBARS")]
    WHPName(whp_name='CTDPRS', whp_unit='DBAR', cf_name='sea_water_pressure')

    If the parameter is unitless use ``None``.:

    >>> WHPNames[("EXPOCODE", None)]
    WHPName(whp_name='EXPOCODE', whp_unit=None, cf_name=None)

    Parameters may also be looked up using ODV style PARAM [UNIT] strings, omitting the [UNIT] for unitless params

    >>> WHPNames["EXPOCODE"]
    WHPName(whp_name='EXPOCODE', whp_unit=None, cf_name=None)
    >>> WHPNames["CTDPRS [DBAR]"]
    WHPName(whp_name='CTDPRS', whp_unit='DBAR', cf_name='sea_water_pressure')

    Parameter aliases also work with ODV style names:

    >>> WHPNames["CTDPRS [DBARS]"]
    WHPName(whp_name='CTDPRS', whp_unit='DBAR', cf_name='sea_water_pressure')
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aliases: dict[WHPNameKey, tuple[str, str | None]] = dict()

    @cached_property
    def odv_names(self):
        """Returns a mapping of ODV style names to WHPName instances"""

        return {to_odv(key): value for key, value in super().items()}

    def __getitem__(self, key: WHPNameKey) -> WHPName:
        unit = None
        flag = False
        error = False

        if isinstance(key, str):
            name, flag = flag_name(key)
            name, unit = normalize_odv_name(name, return_parts=True)
        elif isinstance(key, tuple) and len(key) == 1:
            name = key[0]
        elif isinstance(key, tuple) and len(key) == 2:
            name, unit = key
        else:
            raise KeyError("whpname keys must be str or a tuple")

        if not flag:
            # try again after all the processing above
            name, flag = flag_name(name)
        name, depth = alt_depth(name)

        alias_key = None
        if (name, unit) in self._aliases:
            alias_key = (name, unit)
            name, unit = self._aliases[(name, unit)]

        if (name, unit) in self.error_cols:
            name, unit = self.error_cols[(name, unit)]
            error = True

        param = super().__getitem__((name, unit))

        if depth > 0:
            param = param.as_depth(depth)

        if flag:
            param = param.as_flag()

        if error:
            param = param.as_error()

        if alias_key is not None:
            param = param.as_alias(*alias_key)

        return param

    def __contains__(self, key: object) -> bool:
        return super().__contains__(key) or key in self.odv_names

    @cached_property
    def error_cols(self):
        """A mapping of all the error names to their corresponding WHPName

        >>> WHPNames.error_cols["C14ERR"]
        WHPName(whp_name='DELC14', whp_unit='/MILLE', cf_name=None)
        """
        return {
            (ex.error_name, ex.whp_unit): (ex.whp_name, ex.whp_unit)
            for ex in self.values()
            if ex.error_name is not None
        }

    def _scope_filter(self, scope: str = "cruise") -> tuple[WHPName, ...]:
        return tuple(sorted(name for name in self.values() if name.scope == scope))

    @cached_property
    def groups(self) -> WHPNameGroups:
        """A namedtuple with the properties: cruise, profile, sample

        Each property is a frozen set of WHPName instances.
        The grouping is by what "scope" the parameter applies to.
        For example, the station id (STNNBR) applies to an entire profile.
        Only "profile" level parameters are allowed to be in CTD headers.

        There are currently no "cruise" level parameters.
        All parameters have a scope.

        >>> WHPNames["EXPOCODE"] in WHPNames.groups.profile
        True
        """
        return WHPNameGroups(
            cruise=frozenset(self._scope_filter("cruise")),
            profile=frozenset(self._scope_filter("profile")),
            sample=frozenset(self._scope_filter("sample")),
        )

    @cached_property
    def legacy_json_schema(self):
        """A JSONSchema draft-04 which describes a valid :class:`_WHPNames.legacy_json` document"""
        return loads(
            files("cchdo.params").joinpath("parameters.schema.json").read_text()
        )

    @cached_property
    def legacy_json(self):
        """Provides the params database in the format expected in the old json database

        The order of the objects is guaranteed to be in the preferred WOCE order by parameter name.
        The ordering of parameters with the same name but different units is arbitrary.

        This property is the corresponding python object and not JSON text, it must still be serialized.
        This property will validate against the schema in :class:`_WHPNames.legacy_json_schema`
        """

        results = list(
            dict.fromkeys(sorted(self.values(), key=lambda x: x.rank)).keys()
        )

        required = ["whp_name", "whp_unit", "flag_w", "data_type", "field_width"]
        params = []
        for result in results:
            p_dict = asdict(result)
            p_dict["data_type"] = p_dict.pop("dtype")

            # cleanup things
            del p_dict["nc_name"]
            del p_dict["rank"]
            del p_dict["analytical_temperature_name"]
            del p_dict["analytical_temperature_units"]
            del p_dict["radiation_wavelength"]
            del p_dict["scattering_angle"]
            del p_dict["excitation_wavelength"]
            del p_dict["emission_wavelength"]
            del p_dict["nc_group"]
            del p_dict["in_erddap"]
            del p_dict["alt_depth"]
            del p_dict["flag_col"]
            del p_dict["error_col"]

            if p_dict["data_type"] == "string":
                del p_dict["numeric_min"]
                del p_dict["numeric_max"]
                del p_dict["numeric_precision"]

            if p_dict["flag_w"] == "no_flags":
                p_dict["flag_w"] = None

            keys_to_del = []
            for k, v in p_dict.items():
                if v is None and k not in required:
                    keys_to_del.append(k)
            for k in keys_to_del:
                del p_dict[k]

            params.append(p_dict)

        return params

    def add_alias(self, alias: WHPNameKey, current: tuple[str, str | None]):
        """Adds an alias to the WHPNames dict for this session only

        Some alias names are a little dangerous to add without larger context.
        For example, in the HOT program, nitrate sensors were tested on the CTD using the name NITRATE [UMOL/KG]
        This cannot be unambigiously mapped to either the CTD or the more common Bottle parameter names.

        :param alias: tuple of (name, unit) to map to an existing name, unit must be None is unitless
        :param currnet: any valid existing WHPNames key
        """
        if alias in self:
            raise ValueError("Cannot override base parameter names")
        if alias in self._aliases:
            ...
            # emit a warning
        if current not in self:
            raise ValueError(f"{current} not in {self}")

        self._aliases[alias] = current


class _CFStandardNames(UserDict[str | None, CFStandardName]): ...


CFStandardNames = _CFStandardNames(_cf_standard_names)
WHPNames = _WHPNames(_whp_names)

for _alias, _canonical in _aliases.items():
    WHPNames.add_alias(_alias, _canonical)
