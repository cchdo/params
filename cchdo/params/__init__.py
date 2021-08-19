from dataclasses import dataclass, field
from importlib.resources import path, read_text
from typing import (
    Literal,
    TypeVar,
    Optional,
    Union,
    Tuple,
    NamedTuple,
    Mapping,
    Dict,
    FrozenSet,
)
from collections.abc import MutableMapping
from functools import cached_property
from json import loads
from contextlib import contextmanager
from math import isnan
from datetime import date, time

from sqlalchemy import select

__all__ = ["CFStandardNames", "WHPNames"]

_mode = "production"


@contextmanager
def database():
    with path("cchdo.params", "params.sqlite3") as f:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(
            f"sqlite:///{f}",
            echo=False,
            connect_args={"check_same_thread": False},
            future=True,
        )
        Session = sessionmaker(bind=engine, future=True)
        with Session() as session:
            yield session


class Config(MutableMapping):
    def __init__(self):
        from .models import Config

        with database() as session:
            self._config = {
                record.key: record.value for record in session.query(Config).all()
            }

    def __getitem__(self, key):
        return self._config[key]

    def __setitem__(self, key, value):
        if _mode != "production":
            from sqlalchemy.orm.exc import NoResultFound
            from .models import Config

            with database() as session:
                try:
                    existing = session.query(Config).filter(Config.key == key).one()
                    existing.value = value
                    session.add(existing)
                    session.commit()
                    self._config[key] = value
                except NoResultFound:
                    raise NotImplementedError("keys can only be updated, not added")
        else:
            raise NotImplementedError("Cannot edit the internal DB in production mode")

    def __delitem__(self, key):
        # For now, lets allow updaing but not removal of config records
        raise NotImplementedError()

    def __iter__(self):
        return iter(self._config)

    def __len__(self):
        return len(self._config)


def _name_getter(cf_name, names_list):
    if cf_name is None:
        return None

    names = list(filter(lambda x: x.cf == cf_name, names_list))

    if not any(names):
        return None

    return names


class WHPNameMixin:
    @cached_property
    def whp(self):
        return _name_getter(self.cf, WHPNames.values())


@dataclass(frozen=True)
class CFStandardName(WHPNameMixin):
    """Dataclass representing a single CF Standard Name

    This class captures the information in the standard name table as properties.
    """

    #: name is the cf standard name itself, comes from the "id" property in the XML
    name: str
    canonical_units: str
    grib: Optional[str]
    amip: Optional[str]
    description: str = field(repr=False, hash=False)

    @property
    def cf(self):
        """Part of the `cf` interface, for :class:`CFStandardName` instances, just returns self"""
        return self


@dataclass(frozen=True)
class WHPName:
    """Dataclass representing a single exchange/WOCE style name + unit pair

    There is a ton of extra information that is meant for use in making CF/netCDF files.
    """

    #: the WOCE style parameter "mnemonic", older names were limited to 6 charicters
    #: so funny things like "SALNTY" rather than "SALINITY" occur
    whp_name: str
    #: the variable name to use in cf compliant netcdf files, must be unique
    nc_name: str = field(repr=False)
    #: The historic ordering of columns in a file are determined by this rank, lower rank comes first.
    #: used for sorting the parameters
    rank: float = field(repr=False)
    #: the string name of the data type of this parameter
    dtype: Literal["string", "decimal", "int"] = field(repr=False)

    #: string of the units for this parameter.
    #:
    #: .. warning::
    #:   Not all unitless parameters will have a value of `None`.
    #:   For example, practical salinity will have "PSS-78" rather than
    #:   empty units.
    whp_unit: Optional[str] = None
    #: Which set of woce flag definitions to use for this parameter
    flag_w: Optional[str] = field(default=None, repr=False)
    #: if one exists, the cf standard name for this parameter/unit pair
    cf_name: Optional[str] = None
    #: The expected minimum value for this parameter/unit pair
    numeric_min: Optional[float] = field(default=None, repr=False)
    #: The expected maximum value for this parameter/unit pair
    numeric_max: Optional[float] = field(default=None, repr=False)
    #: The historic print precision for this parameter
    #:
    #: .. danger::
    #:   The use of print precisions as an approximation for uncertainty should only be used if there is no other source of uncertainty.
    numeric_precision: Optional[int] = field(default=None, repr=False)
    #: The print field width
    field_width: Optional[int] = field(default=None, repr=False)
    #: A brief description of the parameter, this is the definition of the parameter
    description: Optional[str] = field(default=None, repr=False)
    #: Any additional notes that are not really part of the definition
    note: Optional[str] = field(default=None, repr=False)
    #: If there is something tricky about this parameter, it should be a warning.
    #: for example, you might interpret the NBR part of the two parameters BTLNBR and STNNBR
    #: as meaning that this field can only have numeric value, this is not correct.
    warning: Optional[str] = field(default=None, repr=False)
    #: Due to historic limitations, there is no standard way of having an error (uncertanty) parameter.
    #: so a mapping is needed.
    error_name: Optional[str] = field(default=None, repr=False)
    #: What the units sould be in a netcdf file, these must be readable by UDUNITS2
    cf_unit: Optional[str] = field(default=None, repr=False)
    #: The calibration scale if not tied to the units, e.g. temperature has ITS-90 and IPTS-68 but bother are deg C or K
    reference_scale: Optional[str] = field(default=None, repr=False)
    #: In woce sum files, the parameters were numbered. Not all parameters have a number, and some parameter numbers present classes
    #: e.g. "hydrocarbon" parameters might all have the same whp_number
    whp_number: Optional[int] = field(default=None, repr=False)
    #: does this parameter apply to an entire cruise, a single profile, or a single sample record (bottle closure or ctd scan)
    scope: str = field(default="sample", repr=False)
    #: If reporting temperature is important, the name of the variable which will have that temperature
    analytical_temperature_name: Optional[str] = field(default=None, repr=False)
    #: If reporting temperature is important, the units of the variable which has the temperature
    analytical_temperature_units: Optional[str] = field(default=None, repr=False)

    @property
    def key(self):
        """WHPNames are uniquely identified by a tuple of their (whp_name, whp_unit) values"""
        return (self.whp_name, self.whp_unit)

    @cached_property
    def data_type(self):
        """the actual python class for this WHPName's dtype

        This is useufl for parsing string values for this WHPName
        """
        if self.dtype == "decimal":
            return float
        if self.dtype == "integer":
            return int
        return str

    @property
    def cf(self) -> Optional[CFStandardName]:
        """The :class:`CFStandardName` equivalent to this WHPName

        Returns none if there does not exist an equivalent :class:`CFStandardName`.
        """
        return CFStandardNames.get(self.cf_name)

    def __eq__(self, other):
        """:class:`WHPName`s are equivalent if their whp_name and whp_unit properties are equivalent"""
        if not isinstance(other, WHPName):
            raise NotImplementedError("Can only compare two WHPName objects")
        return (self.whp_name == other.whp_name) and (self.whp_unit == other.whp_unit)

    def __lt__(self, other):
        """Sorts WHPNames based on their rank property"""
        if not isinstance(other, WHPName):
            raise NotImplementedError("Can only compare two WHPName objects")
        if self.rank == other.rank:
            return str(self.whp_unit) < str(other.whp_unit)
        return self.rank < other.rank

    def get_nc_attrs(self, error=False):
        """a dict containing the netCDF variable attributes needed for CF compliance for this variable"""
        attrs = {
            "whp_name": self.whp_name,
        }

        if error is True and self.error_name is not None:
            attrs["whp_name"] = self.error_name

        if self.whp_unit is not None:
            attrs["whp_unit"] = self.whp_unit

        if self.cf_name is not None:
            standard_name = f"{self.cf.name}"
            if error is True:
                standard_name = f"{standard_name} standard_error"

            attrs["standard_name"] = standard_name
            attrs["units"] = self.cf.canonical_units

        if self.cf_unit is not None:
            attrs["units"] = self.cf_unit

        if self.reference_scale is not None:
            attrs["reference_scale"] = self.reference_scale

        if self.field_width is not None and self.numeric_precision is not None:
            attrs["C_format"] = f"%{self.field_width}.{self.numeric_precision}f"

        return attrs

    def strfex(
        self,
        value,
        flag: bool = False,
        numeric_precision_override: Optional[int] = None,
    ) -> str:
        """Format a value using standard WHP Exchange conventions:

        * dates are formatted as %Y%m%d
        * times are formatted as %H%M
        * fill values are "-999" for data, 9 for flags
        * for floating points, only NaN values are considered to be "fill", there
          are parameters which can have -999 as a real value

        :param value: the value to format as a string, the accepted inputs depends on the :class:`WHPName.dtype`,
                      dates and times are expected to be real `datetime.date` and `datetime.time` objects
        :param boolean flag: should `value` be interpreted as a WOCE flag
        :param int numeric_precision_override: if not None, will overrride the builtin databases :class:`WHPName.numeric_precision`
                                               when formatting floats

        :returns: `value` as a string for printing in a WHP Exchange file
        :rtype: str
        """
        if flag is True and not isnan(value):
            return f"{int(value):d}"
        elif flag is True:
            return "9"

        # https://github.com/python/mypy/issues/5485
        if self.data_type == str:  # type: ignore
            if isinstance(value, date):
                return f"{value:%Y%m%d}"
            if isinstance(value, time):
                return f"{value:%H%M}"
            formatted = f"{str(value):{self.field_width}s}"
            # having empty cells is undesireable
            if formatted.strip() == "":
                return f"{'-999':{self.field_width}s}"

            return formatted
        if self.data_type == int:  # type: ignore
            if isnan(value):
                return f"{-999:{self.field_width}d}"
            return f"{int(value):{self.field_width}d}"

        # we must have a float
        if isnan(value):
            return f"{-999:{self.field_width}.0f}"

        numeric_precision = self.numeric_precision
        if numeric_precision_override is not None:
            numeric_precision = numeric_precision_override

        return f"{value:{self.field_width}.{numeric_precision}f}"


def _load_cf_standard_names(__versions__):
    cf_standard_names: Dict[str, CFStandardName] = {}

    with database() as session:
        from .models import CFName as CFNameDB
        from .models import CFAlias as CFAliasDB

        for record in session.execute(select(CFNameDB)).scalars().all():
            cf_standard_names[record.standard_name] = record.dataclass

        for record in session.execute(select(CFAliasDB)).scalars().all():
            cf_standard_names[record.alias] = cf_standard_names[record.standard_name]

    return cf_standard_names


def _load_whp_names():
    whp_name = {}
    with database() as session:
        from .models import WHPName as WHPNameDB
        from .models import Alias as AliasDB

        for record in session.execute(select(WHPNameDB)).scalars().all():
            param = record.dataclass
            whp_name[param.key] = param

        for record in session.execute(select(AliasDB)).scalars().all():
            whp_name[(record.old_name, record.old_unit)] = whp_name[
                (record.whp_name, record.whp_unit)
            ]

    return whp_name


K = TypeVar("K")
V = TypeVar("V")


class _LazyMapping(Mapping[K, V]):
    def __init__(self, loader):
        self._loader = loader

    @cached_property
    def _cached_dict(self) -> Mapping[K, V]:
        return self._loader()

    def __getitem__(self, key: K) -> V:
        return self._cached_dict[key]

    def __iter__(self):
        for key in self._cached_dict:
            yield key

    def __len__(self) -> int:
        return len(self._cached_dict)


class WHPNameGroups(NamedTuple):
    cruise: FrozenSet[WHPName]
    profile: FrozenSet[WHPName]
    sample: FrozenSet[WHPName]


class _WHPNames(_LazyMapping[Union[str, tuple], WHPName]):
    """A Mapping (i.e. dict) providing a lookup between a WOCE style param and unit to an instance of :class:`WHPName`

    .. warning::
      This class should not be directly used, instead use the premade :data:`WHPNames` instance from this module

    Parameters are looked up using a tuple of `(name, unit)` as strings.

    >>> WHPNames[("CTDPRS", "DBARS")]
    WHPName(whp_name='CTDPRS', whp_unit='DBAR', cf_name='sea_water_pressure')

    If the parameter is unitless use ``None``.:

    >>> WHPNames[("EXPOCODE", None)]
    WHPName(whp_name='EXPOCODE', whp_unit=None, cf_name=None)

    As a convience, unitless params may be looked up via their name alone:

    >>> WHPNames["EXPOCODE"]
    WHPName(whp_name='EXPOCODE', whp_unit=None, cf_name=None)
    """

    def __getitem__(self, key) -> WHPName:
        if isinstance(key, str):
            key = (key, None)

        if isinstance(key, tuple) and len(key) == 1:
            key = (*key, None)

        return self._cached_dict[key]

    @property
    def error_cols(self) -> Dict[str, WHPName]:
        """A mapping of all the error names to their corresponding WHPName

        >>> WHPNames.error_cols["C14ERR"]
        WHPName(whp_name='DELC14', whp_unit='/MILLE', cf_name=None)
        """
        return {
            ex.error_name: ex
            for ex in self._cached_dict.values()
            if ex.error_name is not None
        }

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
        with database() as session:

            from .models import WHPName, Param, Unit

            results = session.execute(
                select(
                    WHPName.whp_name,
                    WHPName.whp_unit,
                    Param.whp_number,
                    WHPName.error_name,
                    Param.flag.label("flag_w"),
                    WHPName.standard_name.label("cf_name"),
                    Unit.cf_unit,
                    Unit.reference_scale,
                    Param.dtype.label("data_type"),
                    WHPName.numeric_min,
                    WHPName.numeric_max,
                    WHPName.numeric_precision,
                    WHPName.field_width,
                    Param.description,
                    Param.note,
                    Param.warning,
                    Param.scope,
                )
                .join(Param)
                .outerjoin(Unit)
                .order_by(Param.rank)
            ).all()

            required = ["whp_name", "whp_unit", "flag_w", "data_type", "field_width"]
            params = []
            for result in results:
                p_dict = result._asdict()

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


class _CFStandardNames(_LazyMapping[Optional[str], CFStandardName]):
    def __init__(self, loader):
        self._loader = loader
        self.__versions__ = {}

    @cached_property
    def _cached_dict(self):
        return self._loader(self.__versions__)


CFStandardNames = _CFStandardNames(_load_cf_standard_names)
WHPNames = _WHPNames(_load_whp_names)
