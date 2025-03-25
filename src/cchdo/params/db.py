from collections.abc import MutableMapping
from contextlib import contextmanager
from importlib.resources import path
from textwrap import dedent

from sqlalchemy import Enum, ForeignKey, ForeignKeyConstraint, Text, create_engine
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.orm.exc import NoResultFound

# these are used in code generators
from . import CFStandardName as CFStandardNameDC
from . import WHPName as WHPNameDC


@contextmanager
def database():
    with path("cchdo.params", "params.sqlite3") as f:
        engine = create_engine(
            f"sqlite:///{f}",
            echo=False,
            connect_args={"check_same_thread": False},
            future=True,
        )
        Session = sessionmaker(bind=engine, future=True)
        with Session() as session:
            yield session


class ConfigDict(MutableMapping):
    def __init__(self):
        with database() as session:
            self._config = {
                record.key: record.value for record in session.query(Config).all()
            }

    def __getitem__(self, key):
        return self._config[key]

    def __setitem__(self, key, value):
        with database() as session:
            try:
                existing = session.query(Config).filter(Config.key == key).one()
                existing.value = value
                session.add(existing)
                session.commit()
                self._config[key] = value
            except NoResultFound:
                raise NotImplementedError("keys can only be updated, not added")

    def __delitem__(self, key):
        # For now, lets allow updaing but not removal of config records
        raise NotImplementedError()

    def __iter__(self):
        return iter(self._config)

    def __len__(self):
        return len(self._config)


class Base(DeclarativeBase): ...


def _str_or_type(val):
    if isinstance(val, str):
        return repr(val)
    return val


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]


class Unit(Base):
    __tablename__ = "ex_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    whp_unit: Mapped[str | None] = mapped_column(unique=True)
    cf_unit: Mapped[str]
    reference_scale: Mapped[str | None]
    note: Mapped[str | None] = mapped_column(Text)


class Param(Base):
    __tablename__ = "ex_params"
    whp_name: Mapped[str] = mapped_column(primary_key=True)
    whp_number: Mapped[int | None]
    description: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    warning: Mapped[str | None] = mapped_column(Text)

    scope: Mapped[str] = mapped_column(
        Enum("cruise", "profile", "sample"), server_default="sample"
    )
    dtype: Mapped[str] = mapped_column(
        Enum("decimal", "integer", "string"),
    )
    flag: Mapped[str] = mapped_column(
        Enum("woce_bottle", "woce_ctd", "woce_discrete", "no_flags"), nullable=False
    )
    ancillary: Mapped[bool] = mapped_column(server_default="0")

    rank: Mapped[float]

    in_erddap: Mapped[bool] = mapped_column(server_default="0")


class CFName(Base):
    __tablename__ = "cf_names"

    standard_name: Mapped[str] = mapped_column(primary_key=True)
    canonical_units: Mapped[str | None]
    grib: Mapped[str | None]
    amip: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)

    @property
    def dataclass(self) -> CFStandardNameDC:
        return eval(self.code)  # noqa

    @property
    def code(self):
        return dedent(
            f"""\
            CFStandardNameDC(
            name={_str_or_type(self.standard_name)},
            canonical_units={_str_or_type(self.canonical_units)},
            grib={_str_or_type(self.grib)},
            amip={_str_or_type(self.amip)},
            description={_str_or_type(self.description)},
            )"""
        )

    def __repr__(self):
        return f"<CFName {self.standard_name=} {self.canonical_units=}>"


class CFAlias(Base):
    __tablename__ = "cf_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str]
    standard_name: Mapped[str] = mapped_column(ForeignKey(CFName.standard_name))

    def __repr__(self):
        return f"<CFAlias {self.alias=} {self.standard_name=}>"


class WHPName(Base):
    __tablename__ = "whp_names"

    whp_name: Mapped[str] = mapped_column(ForeignKey(Param.whp_name), primary_key=True)
    whp_unit: Mapped[str | None] = mapped_column(
        ForeignKey(Unit.whp_unit), primary_key=True
    )
    standard_name: Mapped[str | None] = mapped_column(
        ForeignKey("CFName.standard_name")
    )
    nc_name: Mapped[str | None] = mapped_column(unique=True)
    nc_group: Mapped[str | None]

    numeric_min: Mapped[float | None]
    numeric_max: Mapped[float | None]

    error_name: Mapped[str | None]

    analytical_temperature_name: Mapped[str | None]
    analytical_temperature_units: Mapped[str | None]

    field_width: Mapped[int]
    numeric_precision: Mapped[int | None]

    param: Mapped[Param] = relationship()
    unit: Mapped[Unit] = relationship()
    cf_unit = association_proxy("unit", "cf_unit")

    # Opticas
    radiation_wavelength: Mapped[float | None]
    scattering_angle: Mapped[float | None]
    excitation_wavelength: Mapped[float | None]
    emission_wavelength: Mapped[float | None]

    __table_args__ = (
        ForeignKeyConstraint(
            ["analytical_temperature_name", "analytical_temperature_units"],
            ["whp_names.whp_name", "whp_names.whp_unit"],
        ),
    )

    @property
    def dataclass(self) -> WHPNameDC:
        return eval(self.code)  # noqa

    @property
    def code(self) -> str:
        reference_scale = None
        if self.unit is not None:
            reference_scale = self.unit.reference_scale

        return dedent(
            f"""\
                WHPNameDC(
                whp_name={_str_or_type(self.whp_name)},
                dtype={_str_or_type(self.param.dtype)},
                in_erddap={_str_or_type(self.param.in_erddap)},
                whp_unit={_str_or_type(self.whp_unit)},
                nc_name={_str_or_type(self.nc_name)},
                flag_w={_str_or_type(self.param.flag)},
                cf_name={_str_or_type(self.standard_name)},
                numeric_min={_str_or_type(self.numeric_min)},
                numeric_max={_str_or_type(self.numeric_max)},
                numeric_precision={_str_or_type(self.numeric_precision)},
                field_width={_str_or_type(self.field_width)},
                description={_str_or_type(self.param.description)},
                note={_str_or_type(self.param.note)},
                warning={_str_or_type(self.param.warning)},
                error_name={_str_or_type(self.error_name)},
                cf_unit={_str_or_type(self.cf_unit)},
                reference_scale={_str_or_type(reference_scale)},
                whp_number={_str_or_type(self.param.whp_number)},
                scope={_str_or_type(self.param.scope)},
                analytical_temperature_name={_str_or_type(self.analytical_temperature_name)},
                analytical_temperature_units={_str_or_type(self.analytical_temperature_units)},
                rank={_str_or_type(self.param.rank)},
                radiation_wavelength={_str_or_type(self.radiation_wavelength)},
                scattering_angle={_str_or_type(self.scattering_angle)},
                excitation_wavelength={_str_or_type(self.excitation_wavelength)},
                emission_wavelength={_str_or_type(self.emission_wavelength)},
                nc_group={_str_or_type(self.nc_group)},
                )"""
        )


class Alias(Base):
    __tablename__ = "whp_alias"
    old_name: Mapped[str] = mapped_column(primary_key=True)
    old_unit: Mapped[str | None] = mapped_column(primary_key=True)
    whp_name: Mapped[str]
    whp_unit: Mapped[str | None]

    __table_args__ = (
        ForeignKeyConstraint(
            ["whp_name", "whp_unit"],
            ["whp_names.whp_name", "whp_names.whp_unit"],
        ),
    )
