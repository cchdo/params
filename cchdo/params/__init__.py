from dataclasses import dataclass, field
from importlib.resources import path
from typing import Optional, Callable, Union
from collections.abc import Mapping
from functools import cached_property

__all__ = ["CFStandardNames", "WHPNames"]


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

    name: str  # is the 'id' property in the xml
    canonical_units: str
    grib: Optional[str]
    amip: Optional[str]
    description: str = field(repr=False, hash=False)

    @property
    def cf(self):
        return self


@dataclass(frozen=True)
class WHPName():
    """Wrapper for WHP parameters.json
    """

    whp_name: str
    data_type: Callable[[str], Union[str, float, int]] = field(repr=False)
    whp_unit: Optional[str] = None
    nc_name: Optional[str] = None
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

    @property
    def key(self):
        """This is the thing that uniquely identifies"""
        return (self.whp_name, self.whp_unit)

    @property
    def cf(self):
        return CFStandardNames.get(self.cf_name)

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

        return attrs


def _load_cf_standard_names(__versions__):
    cf_standard_names = {}

    with path("cchdo.params", "params.sqlite3") as f:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from .models import CFName as CFNameDB

        engine = create_engine(f'sqlite:///{f}', echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()

        for record in session.query(CFNameDB).all():
            cf_standard_names[record.standard_name] = record.dataclass

        #if element.tag == "alias":
        #    cf_standard_names[name] = cf_standard_names[name_info["entry_id"]]

    return cf_standard_names



def _load_whp_names():
    _dtype_map = {"string": str, "decimal": float, "integer": int}
    whp_name = {}
    with path("cchdo.params", "params.sqlite3") as f:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(f'sqlite:///{f}', echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()

        from .models import WHPName as WHPNameDB
        from .models import Alias as AliasDB

        for record in session.query(WHPNameDB).all():
            param = record.dataclass
            whp_name[param.key] = param

        for record in session.query(AliasDB).all():
            whp_name[(record.old_name, record.old_unit)] = whp_name[
                (record.whp_name, record.whp_unit)
            ]

    return whp_name


class _LazyMapping(Mapping):
    def __init__(self, loader):
        self._loader = loader

    @cached_property
    def _cached_dict(self):
        return self._loader()

    def _load_data(self):
        self._cached_dict

    def __getitem__(self, key):
        return self._cached_dict[key]

    def __iter__(self):
        for key in self._cached_dict:
            yield key

    def __len__(self):
        return len(self._cached_dict)


class _WHPNames(_LazyMapping):
    def __getitem__(self, key):
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


class _CFStandardNames(_LazyMapping):
    def __init__(self, loader):
        self._loader = loader
        self.__versions__ = {}

    @cached_property
    def _cached_dict(self):
        return self._loader(self.__versions__)


CFStandardNames = _CFStandardNames(_load_cf_standard_names)
WHPNames = _WHPNames(_load_whp_names)
