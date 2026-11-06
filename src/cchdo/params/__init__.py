from collections import UserDict
from dataclasses import asdict
from functools import cached_property
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from json import loads
from logging import getLogger
from typing import Any, NamedTuple

from ._cf_names import cf_standard_names as _cf_standard_names
from ._whp_names import _aliases
from ._whp_names import whp_names as _whp_names
from .core import CFStandardName, WHPName, WHPNameParts

__all__ = ["CFStandardNames", "WHPNames"]

try:
    __version__ = version("cchdo.params")
except PackageNotFoundError:
    __version__ = "999"

WHPNameKey = str | WHPName

logger = getLogger(__name__)


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


def normalize_odv_name(name: WHPNameKey) -> WHPNameParts:
    alt = ""
    flag = ""
    url = ""

    if isinstance(name, WHPName):
        return name._name_parts

    if (url_removed := name.removesuffix("_URL")) != name:
        url = "_URL"
        name = url_removed
    if (flag_removed := name.removesuffix("_FLAG_W")) != name:
        flag = "_FLAG_W"
        name = flag_removed
    if "_ALT_" in name:
        name, depth = name.split("_ALT_")
        try:
            depth = int(depth)
        except ValueError as err:
            raise ValueError("Could not parse _ALT_ level") from err
        alt = f"_ALT_{depth}"

    if name.count("[") != name.count("]"):
        raise ValueError("Unbalanced unit brackets")
    units_start = name.find("[")
    units_end = name.rfind("]")
    if units_start == -1:
        units_start = units_end = len(name)

    base = name[:units_start].strip()
    unit = name[units_start + 1 : units_end].strip()

    # handle the case of including None units e.g. ensure "EXPOCODE [None]" works
    if unit.lower() in ("none", "nan"):
        unit = ""

    return WHPNameParts(base=base, unit=unit, alt=alt, flag=flag, url=url)


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
        self._aliases: dict[WHPNameKey, WHPNameKey] = dict()

    @cached_property
    def odv_names(self):
        """Returns a mapping of ODV style names to WHPName instances"""

        return {name.odv_key: name for name in super().values()}

    @cached_property
    def _nc_names(self) -> dict[str, WHPName]:
        return {param.nc_name: param for param in self.values()}

    def from_nc_name(self, key: str) -> WHPName:
        is_flag = key.endswith("_qc")
        key = key.removesuffix("_qc")
        is_error = key.endswith("_error")
        key = key.removesuffix("_error")
        depth = 0
        if "_alt_" in key:
            try:
                _key, _depth = key.split("_alt_")
                depth = int(_depth)
                key = _key
            except ValueError:
                ...
        param = self._nc_names[key]
        if depth > 0:
            param = param.as_depth(depth)
        if is_flag:
            return param.as_flag()
        if is_error:
            return param.as_error()
        return param

    def __getitem__(self, key: WHPNameKey) -> WHPName:
        error = False
        alias_key = self._aliases.get(key)
        try:
            whpname_parts = normalize_odv_name(alias_key or key)
        except ValueError as err:
            raise KeyError(key) from err
        except AttributeError as err:
            if "tuple" in str(err):
                raise KeyError(
                    "'tuple' object lookups are no longer supported, use ODV style strings instead"
                ) from err
            raise KeyError(key) from err

        base = whpname_parts.base
        if whpname_parts.base in self.error_cols:
            base = self.error_cols[base]
            error = True

        if whpname_parts.unit == "":
            internal_key = base
        else:
            internal_key = f"{base} [{whpname_parts.unit}]"

        param = super().__getitem__(internal_key)

        if whpname_parts.alt != "":
            depth = int(whpname_parts.alt.removeprefix("_ALT_"))
            param = param.as_depth(depth)

        if whpname_parts.flag != "":
            param = param.as_flag()

        if error:
            param = param.as_error()

        if whpname_parts.url:
            param = param.as_url()

        if alias_key is not None:
            param = param.as_alias(key)
            logger.info(f"{param} found using alias {key}")

        return param

    def __contains__(self, key: Any) -> bool:
        if super().__contains__(key):
            return True
        try:
            self[key]
            return True
        except KeyError:
            return False

    @cached_property
    def error_cols(self) -> dict[str, str]:
        """A mapping of all the error names to their corresponding WHPName

        >>> WHPNames.error_cols["C14ERR"]
        "DELC14"
        """
        return {
            ex.error_name: ex.whp_name
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
            del p_dict["url_col"]

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

    def add_alias(self, alias: WHPNameKey, current: WHPNameKey):
        """Adds an alias to the WHPNames dict for this session only

        Some alias names are a little dangerous to add without larger context.
        For example, in the HOT program, nitrate sensors were tested on the CTD using the name NITRATE [UMOL/KG]
        This cannot be unambiguously mapped to either the CTD or the more common Bottle parameter names.

        :param alias: tuple of (name, unit) to map to an existing name, unit must be None is unitless
        :param current: any valid existing WHPNames key
        """
        if alias in self:
            raise ValueError("Cannot override base parameter names")
        if alias in self._aliases:
            ...
            # emit a warning?

        self[current]  # this needs to not raise

        self._aliases[alias] = current


class _CFStandardNames(UserDict[str, CFStandardName]): ...


def default_cf_standard_names() -> _CFStandardNames:
    return _CFStandardNames(_cf_standard_names)


def default_whp_names() -> _WHPNames:
    whpnames = _WHPNames(_whp_names)

    for _alias, _canonical in _aliases.items():
        whpnames.add_alias(_alias, _canonical)

    return whpnames


CFStandardNames = default_cf_standard_names()
WHPNames = default_whp_names()
