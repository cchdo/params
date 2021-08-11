from dataclasses import dataclass, field
from importlib.resources import path, read_text
from typing import TypeVar, Optional, Callable, Union, Tuple, NamedTuple, Mapping, Dict
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
    """Wrapper for CF Standard Names"""

    #: name is the cf standard name itself, comes from the "id" property in the XML
    name: str
    canonical_units: str
    grib: Optional[str]
    amip: Optional[str]
    description: str = field(repr=False, hash=False)

    @property
    def cf(self):
        return self


@dataclass(frozen=True)
class WHPName:
    """Wrapper for WHP parameters.json"""

    whp_name: str
    nc_name: str = field(repr=False)
    rank: float = field(repr=False)  # used for sorting in the "classic" WHP order
    data_type: Callable[[str], Union[str, float, int]] = field(repr=False)

    whp_unit: Optional[str] = None
    flag_w: Optional[str] = field(default=None, repr=False)
    cf_name: Optional[str] = None
    numeric_min: Optional[float] = field(default=None, repr=False)
    numeric_max: Optional[float] = field(default=None, repr=False)
    numeric_precision: Optional[int] = field(default=None, repr=False)
    field_width: Optional[int] = field(default=None, repr=False)
    description: Optional[str] = field(default=None, repr=False)
    note: Optional[str] = field(default=None, repr=False)
    warning: Optional[str] = field(default=None, repr=False)
    error_name: Optional[str] = field(default=None, repr=False)
    cf_unit: Optional[str] = field(default=None, repr=False)
    reference_scale: Optional[str] = field(default=None, repr=False)
    whp_number: Optional[int] = field(default=None, repr=False)
    scope: str = field(default="sample", repr=False)
    analytical_temperature_name: Optional[str] = field(default=None, repr=False)
    analytical_temperature_units: Optional[str] = field(default=None, repr=False)

    @property
    def key(self):
        """This is the thing that uniquely identifies"""
        return (self.whp_name, self.whp_unit)

    @property
    def cf(self) -> Optional[CFStandardName]:
        return CFStandardNames.get(self.cf_name)

    def __eq__(self, other):
        if not isinstance(other, WHPName):
            raise NotImplementedError("Can only compare two WHPName objects")
        return (self.whp_name == other.whp_name) and (self.whp_unit == other.whp_unit)

    def __lt__(self, other):
        if not isinstance(other, WHPName):
            raise NotImplementedError("Can only compare two WHPName objects")
        if self.rank == other.rank:
            return str(self.whp_unit) < str(other.whp_unit)
        return self.rank < other.rank

    def get_nc_attrs(self, error=False):
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
    cruise: Tuple[WHPName, ...]
    profile: Tuple[WHPName, ...]
    sample: Tuple[WHPName, ...]


class _WHPNames(_LazyMapping[Union[str, tuple], WHPName]):
    def __getitem__(self, key) -> WHPName:
        if isinstance(key, str):
            key = (key, None)

        if isinstance(key, tuple) and len(key) == 1:
            key = (*key, None)

        return self._cached_dict[key]

    @property
    def error_cols(self):
        return {
            ex.error_name: ex
            for ex in self._cached_dict.values()
            if ex.error_name is not None
        }

    def _scope_filter(self, scope: str = "cruise") -> Tuple[WHPName, ...]:
        return tuple(sorted(name for name in self.values() if name.scope == scope))

    @cached_property
    def groups(self):
        return WHPNameGroups(
            cruise=self._scope_filter("cruise"),
            profile=self._scope_filter("profile"),
            sample=self._scope_filter("sample"),
        )

    @cached_property
    def legacy_json_schema(self):
        return loads(read_text("cchdo.params", "parameters.schema.json"))

    @cached_property
    def legacy_json(self):
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
