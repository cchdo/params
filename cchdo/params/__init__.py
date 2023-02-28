from collections import UserDict
from dataclasses import asdict
from functools import cached_property
from importlib.resources import read_text
from json import loads
from typing import FrozenSet, NamedTuple, Optional, Tuple, Union

from ._cf_names import cf_standard_names as _cf_standard_names
from ._whp_names import whp_names as _whp_names
from .core import CFStandardName, WHPName

__all__ = ["CFStandardNames", "WHPNames"]


WHPNameKey = Union[str, Tuple[str, Optional[str]], Tuple[str]]


def to_odv(key: Tuple[str, Optional[str]]):
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
    cruise: FrozenSet[WHPName]
    profile: FrozenSet[WHPName]
    sample: FrozenSet[WHPName]


class _WHPNames(UserDict[WHPNameKey, WHPName]):
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

    @cached_property
    def odv_names(self):
        """Returns a mapping of ODV style names to WHPName instances"""

        return {to_odv(key): value for key, value in self.data.items()}

    def __getitem__(self, key: WHPNameKey) -> WHPName:
        if isinstance(key, str):
            try:
                return self.odv_names[key]
            except KeyError:
                pass

            key = (key, None)

        if isinstance(key, tuple) and len(key) == 1:
            key = (key[0], None)

        return self.data[key]

    def __contains__(self, key: object) -> bool:
        return key in self.data or key in self.odv_names

    @cached_property
    def error_cols(self):
        """A mapping of all the error names to their corresponding WHPName

        >>> WHPNames.error_cols["C14ERR"]
        WHPName(whp_name='DELC14', whp_unit='/MILLE', cf_name=None)
        """
        error_dict = {
            (ex.error_name, ex.whp_unit): ex
            for ex in self.data.values()
            if ex.error_name is not None
        }
        for key, param in list(error_dict.items()):
            error_dict[to_odv(key)] = param

        return error_dict

    def _scope_filter(self, scope: str = "cruise") -> Tuple[WHPName, ...]:
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
        return loads(read_text("cchdo.params", "parameters.schema.json"))

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

    def add_alias(
        self, alias: Union[Tuple[str, str], Tuple[str, None]], current: WHPNameKey
    ):
        """Adds an alias to the WHPNames dict for this session only

        Some alias names are a little dangerous to add without larger context.
        For example, in the HOT program, nitrate sensors were tested on the CTD using the name NITRATE [UMOL/KG]
        This cannot be unambigiously mapped to either the CTD or the more common Bottle parameter names.

        :param alias: tuple of (name, unit) to map to an existing name, unit must be None is unitless
        :param currnet: any valid existing WHPNames key
        """
        if not isinstance(alias, tuple):
            raise TypeError("Alias key must be a tuple")
        if len(alias) != 2:
            raise ValueError("Alias key must have two elements")
        if not isinstance(alias[0], str) or not isinstance(alias[1], (str, type(None))):
            raise TypeError("Alias key must be either (str. str) or (str, None)")
        if alias in self.data:
            raise ValueError("Cannot add duplicate key")

        self.data[alias] = self[current]


class _CFStandardNames(UserDict[Optional[str], CFStandardName]):
    ...


CFStandardNames = _CFStandardNames(_cf_standard_names)
WHPNames = _WHPNames(_whp_names)
