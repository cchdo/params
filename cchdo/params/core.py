from dataclasses import dataclass, field, replace
from datetime import date, time
from math import isnan
from typing import Literal


@dataclass(frozen=True)
class CFStandardName:
    """Dataclass representing a single CF Standard Name

    This class captures the information in the standard name table as properties.
    """

    #: name is the cf standard name itself, comes from the "id" property in the XML
    name: str
    canonical_units: str | None
    grib: str | None
    amip: str | None
    description: str | None = field(repr=False, hash=False)

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
    #: if CF wants this variable collaposed into something with extra dimmensions
    #: the final variable will have this name
    nc_group: str | None = field(repr=False)
    #: The historic ordering of columns in a file are determined by this rank, lower rank comes first.
    #: used for sorting the parameters
    rank: float = field(repr=False)
    #: the string name of the data type of this parameter
    dtype: Literal["string", "decimal", "integer"] = field(repr=False)

    #: indicates if this variable should appear in the CCHDO/NOAA ERDDAP
    in_erddap: bool = field(repr=False)

    #: The print field width
    field_width: int = field(repr=False)

    #: string of the units for this parameter.
    #:
    #: .. warning::
    #:   Not all unitless parameters will have a value of `None`.
    #:   For example, practical salinity will have "PSS-78" rather than
    #:   empty units.
    whp_unit: str | None = None
    #: Which set of woce flag definitions to use for this parameter
    flag_w: Literal["woce_discrete", "woce_ctd", "no_flags", "woce_bottle"] | None = (
        field(default=None, repr=False)
    )
    #: if one exists, the cf standard name for this parameter/unit pair
    cf_name: str | None = None
    #: The expected minimum value for this parameter/unit pair
    numeric_min: float | None = field(default=None, repr=False)
    #: The expected maximum value for this parameter/unit pair
    numeric_max: float | None = field(default=None, repr=False)
    #: The historic print precision for this parameter
    #:
    #: .. danger::
    #:   The use of print precisions as an approximation for uncertainty should only be used if there is no other source of uncertainty.
    numeric_precision: int | None = field(default=None, repr=False)
    #: A brief description of the parameter, this is the definition of the parameter
    description: str | None = field(default=None, repr=False)
    #: Any additional notes that are not really part of the definition
    note: str | None = field(default=None, repr=False)
    #: If there is something tricky about this parameter, it should be a warning.
    #: for example, you might interpret the NBR part of the two parameters BTLNBR and STNNBR
    #: as meaning that this field can only have numeric value, this is not correct.
    warning: str | None = field(default=None, repr=False)
    #: Due to historic limitations, there is no standard way of having an error (uncertanty) parameter.
    #: so a mapping is needed.
    error_name: str | None = field(default=None, repr=False)
    #: What the units sould be in a netcdf file, these must be readable by UDUNITS2
    cf_unit: str | None = field(default=None, repr=False)
    #: The calibration scale if not tied to the units, e.g. temperature has ITS-90 and IPTS-68 but bother are deg C or K
    reference_scale: str | None = field(default=None, repr=False)
    #: In woce sum files, the parameters were numbered. Not all parameters have a number, and some parameter numbers present classes
    #: e.g. "hydrocarbon" parameters might all have the same whp_number
    whp_number: int | None = field(default=None, repr=False)
    #: does this parameter apply to an entire cruise, a single profile, or a single sample record (bottle closure or ctd scan)
    scope: str = field(default="sample", repr=False)
    #: If reporting temperature is important, the name of the variable which will have that temperature
    analytical_temperature_name: str | None = field(default=None, repr=False)
    #: If reporting temperature is important, the units of the variable which has the temperature
    analytical_temperature_units: str | None = field(default=None, repr=False)

    # optics stuff
    radiation_wavelength: float | None = field(default=None, repr=False)
    scattering_angle: float | None = field(default=None, repr=False)
    excitation_wavelength: float | None = field(default=None, repr=False)
    emission_wavelength: float | None = field(default=None, repr=False)

    # API Things
    alt_depth: int = field(default=0, repr=False)
    #: If this param represents an alternate parameter, how deep in the alternates are we.
    #: This is 0 for the builtin params
    whp_name_alias: str | None = field(default=None, repr=False, compare=False)
    #: If this param was instianciated from an alias, what was that alias name
    whp_unit_alias: str | None = field(default=None, repr=False, compare=False)
    #: If this param was instantiated from an alias, what was that alias unit
    error_col: bool = field(default=False)
    #: The name that found this param was for the uncertainty/error name
    flag_col: bool = field(default=False)
    #: The name that found this param was for the flag name (with units)

    def as_depth(self, depth: int) -> "WHPName":
        return replace(self, alt_depth=depth)

    def as_alias(self, param, unit) -> "WHPName":
        return replace(self, whp_name_alias=param, whp_unit_alias=unit)

    def as_error(self) -> "WHPName":
        if self.flag_col is True:
            raise ValueError("flag columns cannot have errors")
        return replace(self, error_col=True)

    def as_flag(self) -> "WHPName":
        if self.error_col is True:
            raise ValueError("error columns cannot have flags")
        return replace(self, flag_col=True)

    @property
    def full_whp_name(self):
        if self.alt_depth > 0:
            return f"{self.whp_name}_ALT_{self.alt_depth}"
        else:
            return self.whp_name

    @property
    def full_nc_name(self):
        if self.alt_depth > 0:
            return f"{self.nc_name}_alt_{self.alt_depth}"
        else:
            return self.nc_name

    @property
    def full_error_name(self):
        if self.alt_depth > 0 and self.error_name is not None:
            return f"{self.error_name}_ALT_{self.alt_depth}"
        else:
            return self.error_name

    @property
    def key(self):
        """WHPNames are uniquely identified by a tuple of their (whp_name, whp_unit) values"""
        return (self.whp_name, self.whp_unit)

    @property
    def odv_key(self) -> str:
        """An ODV style representation of the param in the form of "NAME [UNIT]"

        Note that the "[UNIT]" part is omitted if there are no units
        """
        if self.error_col:
            base = self.full_error_name
        else:
            base = self.full_whp_name

        if self.whp_unit is None:
            key = base
        else:
            key = f"{base} [{self.whp_unit}]"

        if self.flag_col:
            key = f"{key}_FLAG_W"

        return key

    @property
    def nc_name_flag(self) -> str:
        """The variable name of the "flag" ancillary variable for this parameter"""
        return f"{self.full_nc_name}_qc"

    @property
    def nc_name_error(self) -> str:
        """The variable name of the uncertainty ancillary variable for this parameter"""
        return f"{self.full_nc_name}_error"

    @property
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
    def cf(self) -> CFStandardName | None:
        """The :class:`CFStandardName` equivalent to this WHPName

        Returns none if there does not exist an equivalent :class:`CFStandardName`.
        """
        from . import CFStandardNames  # noqa

        return CFStandardNames.get(self.cf_name)

    def __eq__(self, other):
        """:class:`WHPName`s are equivalent if their whp_name and whp_unit properties are equivalent"""
        if not isinstance(other, WHPName):
            raise NotImplementedError("Can only compare two WHPName objects")
        return (
            (self.whp_name == other.whp_name)
            and (self.whp_unit == other.whp_unit)
            and (self.alt_depth == other.alt_depth)
        )

    def __hash__(self):
        return hash((self.whp_name, self.whp_unit, self.alt_depth))

    def __lt__(self, other):
        """Sorts WHPNames based on their rank property"""
        if not isinstance(other, WHPName):
            raise NotImplementedError("Can only compare two WHPName objects")
        if (self.rank == other.rank) and (self.alt_depth != other.alt_depth):
            return self.alt_depth < other.alt_depth
        if self.rank == other.rank:
            return str(self.whp_unit) < str(other.whp_unit)
        return self.rank < other.rank

    def __repr__(self):
        base = f'"{self.odv_key}"'
        if self.flag_col:
            base += ", flag=True"
        if self.error_col:
            base += ", error=True"
        if self.alt_depth > 0:
            base += f", depth={self.alt_depth}"
        return f"WHPName({base})"

    def get_nc_attrs(self, error=False):
        """a dict containing the netCDF variable attributes needed for CF compliance for this variable"""
        attrs = {
            "whp_name": self.full_whp_name,
        }

        if error is True and self.full_error_name is not None:
            attrs["whp_name"] = self.full_error_name

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
            attrs["C_format_source"] = "database"

        return attrs

    def strfex(
        self,
        value,
        flag: bool = False,
        numeric_precision_override: int | None = None,
        date_or_time: Literal["date", "time"] | None = None,
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
        if self.dtype == "string":
            if isinstance(value, date) or date_or_time == "date":
                return f"{value:%Y%m%d}"
            if isinstance(value, time) or date_or_time == "time":
                return f"{value:%H%M}"
            formatted = f"{str(value):{self.field_width}s}"
            # having empty cells is undesireable
            if formatted.strip() == "":
                return f"{'-999':{self.field_width}s}"

            return formatted
        if self.dtype == "integer":
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
