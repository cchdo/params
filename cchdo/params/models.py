from textwrap import dedent
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Enum,
    Float,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.ext.associationproxy import association_proxy

# these are used in code generators
from . import WHPName as WHPNameDC  # noqa
from . import CFStandardName as CFStandardNameDC  # noqa


Base = declarative_base()


def _str_or_type(val):
    if isinstance(val, str):
        return repr(val)
    return val


class Config(Base):
    __tablename__ = "config"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


class Unit(Base):
    __tablename__ = "ex_units"

    id = Column(Integer, primary_key=True)
    whp_unit = Column(String, nullable=True, unique=True)
    cf_unit = Column(String, nullable=False)
    reference_scale = Column(String, nullable=True)
    note = Column(Text, nullable=True)


class Param(Base):
    __tablename__ = "ex_params"
    whp_name = Column(String, primary_key=True)
    whp_number = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    warning = Column(Text, nullable=True)

    scope = Column(
        Enum("cruise", "profile", "sample"), nullable=False, server_default="sample"
    )
    dtype = Column(
        Enum("decimal", "integer", "string"),
        nullable=False,
    )
    flag = Column(
        Enum("woce_bottle", "woce_ctd", "woce_discrete", "no_flags"), nullable=False
    )
    ancillary = Column(Boolean, nullable=False, server_default="0")

    rank = Column(Float, nullable=False)


class CFName(Base):
    __tablename__ = "cf_names"

    standard_name = Column(String, primary_key=True)
    canonical_units = Column(String, nullable=True)
    grib = Column(String, nullable=True)
    amip = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    @property
    def dataclass(self):
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

    id = Column(
        Integer, primary_key=True
    )  # cannot use numeric id since alias isn't unique
    alias = Column(String, nullable=False)
    standard_name = Column(
        String, ForeignKey(CFName.__table__.c.standard_name), nullable=False
    )

    def __repr__(self):
        return f"<CFAlias {self.alias=} {self.standard_name=}>"


class WHPName(Base):
    __tablename__ = "whp_names"

    whp_name = Column(String, ForeignKey(Param.__table__.c.whp_name), primary_key=True)
    whp_unit = Column(
        String, ForeignKey(Unit.__table__.c.whp_unit), primary_key=True, nullable=True
    )
    standard_name = Column(
        String, ForeignKey(CFName.__table__.c.standard_name), nullable=True
    )
    nc_name = Column(String, unique=True, nullable=True)
    nc_group = Column(String, unique=True, nullable=True)

    numeric_min = Column(Float, nullable=True)
    numeric_max = Column(Float, nullable=True)

    error_name = Column(String, nullable=True)

    analytical_temperature_name = Column(String, nullable=True)
    analytical_temperature_units = Column(String, nullable=True)

    field_width = Column(Integer, nullable=False)
    numeric_precision = Column(Integer, nullable=True)

    param: Param = relationship("Param")
    unit: Unit = relationship("Unit")
    cf_unit = association_proxy("unit", "cf_unit")

    # Opticas
    radiation_wavelength = Column(Float, nullable=True)
    scattering_angle = Column(Float, nullable=True)
    excitation_wavelength = Column(Float, nullable=True)
    emission_wavelength = Column(Float, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["analytical_temperature_name", "analytical_temperature_units"],
            ["whp_names.whp_name", "whp_names.whp_unit"],
        ),
    )

    @property
    def dataclass(self):
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
    old_name = Column(String, primary_key=True)
    old_unit = Column(String, primary_key=True, nullable=True)
    whp_name = Column(String)
    whp_unit = Column(String)

    __table_args__ = (
        ForeignKeyConstraint(
            ["whp_name", "whp_unit"],
            ["whp_names.whp_name", "whp_names.whp_unit"],
        ),
    )
