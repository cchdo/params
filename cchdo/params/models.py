from sqlalchemy import UniqueConstraint, CheckConstraint, Column, Integer, String, Text, Enum, Float, Boolean, ForeignKey, ForeignKeyConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.associationproxy import association_proxy

Base = declarative_base()

class Unit(Base):
    __tablename__ = 'ex_units'
    
    id = Column(Integer, primary_key=True)
    whp_unit = Column(String, nullable=True, unique=True)
    cf_unit = Column(String, nullable=False)
    reference_scale = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    
class Param(Base):
    __tablename__ = 'ex_params'
    whp_name = Column(String, primary_key=True)
    whp_number = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    warning = Column(Text, nullable=True)
    
    scope = Column(Enum('cruise', 'profile', 'sample'), nullable=False, server_default='sample')
    dtype = Column(Enum('decimal', 'integer', 'string'), nullable=False, )
    flag = Column(Enum('woce_bottle', 'woce_ctd', 'woce_discrete', 'no_flags'), nullable=False)
    ancillary = Column(Boolean, nullable=False, server_default='0')
    
    rank = Column(Float, nullable=False)
    

class CFName(Base):
    __tablename__ = 'cf_names'
    
    standard_name = Column(String, primary_key=True)
    canonical_units = Column(String, nullable=True)
    grib = Column(String, nullable=True)
    amip = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    @property
    def dataclass(self):
        from . import CFStandardName as CFStandardNameDC
        return CFStandardNameDC(
            name=self.standard_name,
            canonical_units=self.canonical_units,
            grib=self.grib,
            amip=self.amip,
            description=self.description,
        )
    
class CFAlias(Base):
    __tablename__ = 'cf_aliases'
    
    id = Column(Integer, primary_key=True) # cannot use numeric id since alias isn't unique
    alias = Column(String, nullable=False)
    standard_name = Column(String, ForeignKey(CFName.__table__.c.standard_name), nullable=False)
    
class WHPName(Base):
    __tablename__ = 'whp_names'
    
    whp_name = Column(String, ForeignKey(Param.__table__.c.whp_name), primary_key=True)
    whp_unit = Column(String, ForeignKey(Unit.__table__.c.whp_unit), primary_key=True, nullable=True)
    standard_name = Column(String, ForeignKey(CFName.__table__.c.standard_name), nullable=True)
    nc_name = Column(String, unique=True, nullable=True)
    
    numeric_min = Column(Float, nullable=True)
    numeric_max = Column(Float, nullable=True)
    
    error_name = Column(String, nullable=True)
    
    analytical_temperature_name = Column(String, nullable=True)
    analytical_temperature_units = Column(String, nullable=True)
    
    field_width = Column(Integer, nullable=False)
    numeric_precision = Column(Integer, nullable=True)

    param = relationship("Param")
    unit = relationship("Unit")
    cf_unit = association_proxy("unit", "cf_unit")
    
    __table_args__ = (
        ForeignKeyConstraint(
            ['analytical_temperature_name', 'analytical_temperature_units'],
            ['whp_names.whp_name', 'whp_names.whp_unit'],
        ),
    )

    @property
    def dataclass(self):
        from . import WHPName as WHPNameDC
        _dtype_map = {"string": str, "decimal": float, "integer": int}

        reference_scale = None
        if self.unit is not None:
            reference_scale = self.unit.reference_scale

        return WHPNameDC(
            whp_name=self.whp_name,
            data_type=_dtype_map[self.param.dtype],
            whp_unit=self.whp_unit,
            nc_name=self.nc_name,
            flag_w=self.param.flag,
            cf_name=self.standard_name,
            numeric_min=self.numeric_min,
            numeric_max=self.numeric_max,
            numeric_precision=self.numeric_precision,
            field_width=self.field_width,
            description=self.param.description,
            note=self.param.note,
            warning=self.param.warning,
            error_name=self.error_name,
            cf_unit=self.cf_unit,
            reference_scale=reference_scale,
            whp_number=self.param.whp_number,
            scope=self.param.scope,
        )
    
class Alias(Base):
    __tablename__ = "whp_alias"
    old_name = Column(String, primary_key=True)
    old_unit = Column(String, primary_key=True, nullable=True)
    whp_name = Column(String)
    whp_unit = Column(String)
    
    __table_args__ = (
        ForeignKeyConstraint(
            ['whp_name', 'whp_unit'],
            ['whp_names.whp_name', 'whp_names.whp_unit'],
        ),
    )
    