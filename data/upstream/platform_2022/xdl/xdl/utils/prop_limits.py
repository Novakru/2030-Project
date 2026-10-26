"""Prop limits are used to validate the input given to xdl elements. For
example, a volume property should be a positive number, optionally followed by
volume units. The prop limit is used to check that input supplied is valid for
that property.
"""

import re
from typing import List, Optional

class PropLimit(object):
    """Convenience class for storing prop limit. A prop limit is essentially a
    regex for validating the input to a given prop. For example, checking
    appropriate units are used or a value is within a certain range.

    Either ``regex`` or ``enum`` must be given when instantiating. If ``enum``
    is given it will override whatever is given for ``regex`` and ``hint``.
    ``hint`` and ``default`` are both optional, but recommended, at least when
    using ``regex`` not ``enum``.

    Arguments:
        regex (str): Regex pattern that should match with valid values and not
            match with invalid values.
        hint (str): Useful hint for what valid value should look like, e.g.
            "Volume should be a number followed by volume units, e.g. '5 mL'."
        default (str): Default valid value. Should use standard units of the
            quantity involved, e.g. for volume, '0 mL'.
        enum (List[str]): List of values that the prop can take. This is used
            to automatically generate a regex from the list of allowed values.
    """
    def __init__(
        self,
        regex: Optional[str] = None,
        hint: Optional[str] = '',
        default: Optional[str] = '',
        enum: Optional[List[str]] = [],
    ):
        if not regex and not enum:
            raise ValueError(
                'Either `regex` or `enum` argument must be given.')

        self.default = default

        # If enum given generate regex from this
        self.enum = enum
        if enum:
            if not regex:
                self.regex = self.generate_enum_regex()
            else:
                self.regex = regex

            if not hint:
                self.hint = self.generate_enum_hint()
            else:
                self.hint = hint

        # Otherwise just set regex as attribute
        else:
            self.regex = regex
            self.hint = hint

    def validate(self, value: str) -> bool:
        """Validate given value against prop limit regex.

        Args:
            value (str): Value to validate against prop limit.

        Returns:
            bool: True if the value matches the prop limit, otherwise False.
        """
        return re.match(self.regex, value) is not None

    def generate_enum_regex(self) -> str:
        """Generate regex from :py:attr:`enum`. Regex will match any of the
        items in :py:attr:`enum`.

        Returns:
            str: Regex that will match any of the strings in the :py:attr:`enum`
                list.
        """
        regex = r'('
        for item in self.enum:
            regex += item + r'|'
        regex = regex[:-1] + r')'
        return regex

    def generate_enum_hint(self) -> str:
        """Generate hint from :py:attr:`enum`. Hint will list all items in
        :py:attr:`enum`.

        Returns:
            str: Hint listing all items in :py:attr:`enum`.
        """
        s = 'Expecting one of '
        for item in self.enum[:-1]:
            s += f'"{item}", '
        s = s[:-2] + f' or "{self.enum[-1]}".'
        return s

##################
# Regex patterns #
##################

#: Pattern to match a positive or negative float,
#: e.g. '0', '-1', '1', '-10.3', '10.3', '0.0' would all be matched by this
#: pattern.
FLOAT_PATTERN: str = r'([-]?[0-9]+(?:[.][0-9]+)?)'

#: Pattern to match a positive float,
#: e.g. '0', 1', '10.3', '0.0' would all be matched by this pattern, but not
#: '-10.3' or '-1'.
POSITIVE_FLOAT_PATTERN: str = r'([0-9]+(?:[.][0-9]+)?)'

#: Pattern to match boolean strings, specifically matching 'true' and 'false'
#: case insensitvely.
BOOL_PATTERN: str = r'(false|False|true|True)'

#: Pattern to match all accepted volumes units case insensitvely, or empty string.
VOLUME_UNITS_PATTERN: str = r'(l|L|litre|litres|liter|liters|ml|mL|cm3|cc|milliltre|millilitres|milliliter|milliliters|cl|cL|centiltre|centilitres|centiliter|centiliters|dl|dL|deciltre|decilitres|deciliter|deciliters|ul|uL|μl|μL|microlitre|microlitres|microliter|microliters)?'

#: Pattern to match all accepted mass units, or empty string.
MASS_UNITS_PATTERN: str = r'(g|gram|grams|kg|kilogram|kilograms|mg|milligram|milligrams|ug|μg|microgram|micrograms)?'

#: Pattern to match all accepted temperature units, or empty string.
TEMP_UNITS_PATTERN: str = r'(°C|K|F)?'

#: Pattern to match all accepted time units, or empty string.
TIME_UNITS_PATTERN = r'(days|day|h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds)?'

#: Pattern to match all accepted pressure units, or empty string.
PRESSURE_UNITS_PATTERN = r'(mbar|bar|torr|Torr|mmhg|mmHg|atm|Pa|pa)?'

#: Pattern to match all accepted rotation speed units, or empty string.
ROTATION_SPEED_UNITS_PATTERN = r'(rpm|RPM)?'

#: Pattern to match all accepted length units, or empty string.
DISTANCE_UNITS_PATTERN = r'(nm|µm|mm|cm|m|km)?'

#: Pattern to match all accepted mol units, or empty string.
MOL_UNITS_PATTERN = r'(mmol|mol)?'

###############
# Prop limits #
###############

def generate_quantity_units_pattern(
    quantity_pattern: str,
    units_pattern: str,
    hint: Optional[str] = '',
    default: Optional[str] = ''
) -> PropLimit:
    """
    Convenience function to generate PropLimit object for different quantity
    types, i.e. for variations on the number followed by unit pattern.

    Args:
        quantity_pattern (str): Pattern to match the number expected. This will
            typically be ``POSITIVE_FLOAT_PATTERN`` or ``FLOAT_PATTERN``.
        units_pattern (str): Pattern to match the units expected or empty
            string. Empty string is matched as not including units is allowed
            as in this case standard units are used.
        hint (str): Hint for the prop limit to tell the user what correct input
            should look like in the case of an errror.
        default (str): Default value for the prop limit, should use standard
            units for the prop involved.
    """
    return PropLimit(
        regex=r'^((' + quantity_pattern + r'[ ]?'\
            + units_pattern + r'$)|(^' + quantity_pattern + r'))$',
        hint=hint,
        default=default
    )

# NOTE: It is important here that defaults use the standard unit for that
# quantity type as XDL app uses this to add in default units.

#: Prop limit for volume props.
VOLUME_PROP_LIMIT: PropLimit = PropLimit(
    regex=r'^(all|(' + POSITIVE_FLOAT_PATTERN + r'[ ]?'\
        + VOLUME_UNITS_PATTERN + r')|(' + POSITIVE_FLOAT_PATTERN + r'))$',
    hint='Expecting number followed by standard volume units, e.g. "5.5 mL"',
    default='0 mL',
)

#: Prop limit for mass props.
MASS_PROP_LIMIT: PropLimit = generate_quantity_units_pattern(
    POSITIVE_FLOAT_PATTERN,
    MASS_UNITS_PATTERN,
    hint='Expecting number followed by standard mass units, e.g. "2.3 g"',
    default='0 g'
)

#: Prop limit for mol props.
MOL_PROP_LIMIT: PropLimit = generate_quantity_units_pattern(
    POSITIVE_FLOAT_PATTERN,
    MOL_UNITS_PATTERN,
    hint='Expecting number followed by mol or mmol, e.g. "2.3 mol".',
    default='0 mol',
)

#: Prop limit for temp props.
TEMP_PROP_LIMIT: PropLimit = generate_quantity_units_pattern(
    FLOAT_PATTERN,
    TEMP_UNITS_PATTERN,
    hint='Expecting number in degrees celsius or number followed by standard temperature units, e.g. "25", "25°C", "298 K".',
    default='25°C',
)

#: Prop limit for time props.
TIME_PROP_LIMIT: PropLimit = generate_quantity_units_pattern(
    POSITIVE_FLOAT_PATTERN,
    TIME_UNITS_PATTERN,
    hint='Expecting number followed by standard time units, e.g. "15 mins", "3 hrs".',
    default='0 secs'
)

#: Prop limit for pressure props.
PRESSURE_PROP_LIMIT: PropLimit = generate_quantity_units_pattern(
    POSITIVE_FLOAT_PATTERN,
    PRESSURE_UNITS_PATTERN,
    hint='Expecting number followed by standard pressure units, e.g. "50 mbar", "1 atm".',
    default='1013.25 mbar'
)

#: Prop limit for rotation speed props.
ROTATION_SPEED_PROP_LIMIT: PropLimit = generate_quantity_units_pattern(
    POSITIVE_FLOAT_PATTERN,
    ROTATION_SPEED_UNITS_PATTERN,
    hint='Expecting RPM value, e.g. "400 RPM".',
    default='400 RPM',
)

#: Prop limit for wavelength props.
WAVELENGTH_PROP_LIMIT: PropLimit = generate_quantity_units_pattern(
    POSITIVE_FLOAT_PATTERN,
    DISTANCE_UNITS_PATTERN,
    hint='Expecting wavelength, e.g. "400 nm".',
    default='400 nm'
)

#: Prop limit for any props requiring a positive integer such as ``repeats``.
#: Used if no explicit property is given and prop type is ``int``.
POSITIVE_INT_PROP_LIMIT: PropLimit = PropLimit(
    r'[0-9]+',
    hint='Expecting positive integer value, e.g. "3"',
    default='1',
)

#: Prop limit for any props requiring a positive float. Used if no explicit
#: prop type is given and prop type is ``float``.
POSITIVE_FLOAT_PROP_LIMIT: PropLimit = PropLimit(
    regex=POSITIVE_FLOAT_PATTERN,
    hint='Expecting positive float value, e.g. "3", "3.5"',
    default='0',
)

#: Prop limit for any props requiring a boolean value. Used if no explicit prop
#: type is given and prop type is ``bool``.
BOOL_PROP_LIMIT: PropLimit = PropLimit(
    BOOL_PATTERN,
    hint='Expecting one of "false" or "true".',
    default='false',
)

#: Prop limit for ``WashSolid`` ``stir`` prop. This is a special case as the
#: value can be ``True``, ``False`` or ``'solvent'``.
WASH_SOLID_STIR_PROP_LIMIT: PropLimit = PropLimit(
    r'(' + BOOL_PATTERN + r'|solvent)',
    enum=['true', 'solvent', 'false'],
    hint='Expecting one of "true", "false" or "solvent".',
    default='True'
)

#: Prop limit for  ``Separate`` ``purpose`` prop. One of 'extract' or 'wash'.
SEPARATION_PURPOSE_PROP_LIMIT: PropLimit = PropLimit(enum=['extract', 'wash'])

#: Prop limit for ``Separate`` ``product_phase`` prop. One of 'top' or 'bottom'.
SEPARATION_PRODUCT_PHASE_PROP_LIMIT: PropLimit = PropLimit(enum=['top', 'bottom'])

#: Prop limit for ``Add`` ``purpose`` prop. One of 'neutralize', 'precipitate',
#: 'dissolve', 'basify', 'acidify' or 'dilute'.
ADD_PURPOSE_PROP_LIMIT = PropLimit(
    enum=[
        'neutralize',
        'precipitate',
        'dissolve',
        'basify',
        'acidify',
    ]
)

#: Prop limit for ``HeatChill`` ``purpose`` prop. One of 'control-exotherm',
#: 'reaction' or 'unstable-reagent'.
HEATCHILL_PURPOSE_PROP_LIMIT = PropLimit(
    enum=['control-exotherm', 'reaction', 'unstable-reagent']
)

#: Prop limit for ``Stir`` ``purpose`` prop. 'dissolve' is only option.
STIR_PURPOSE_PROP_LIMIT = PropLimit(
    enum=['dissolve']
)

#: Prop limit for ``Reagent`` ``role`` prop. One of 'solvent', 'reagent',
#: 'catalyst', 'substrate', 'acid', 'base' or 'activating-agent'.
REAGENT_ROLE_PROP_LIMIT = PropLimit(
    enum=[
        'solvent',
        'reagent',
        'catalyst',
        'substrate',
        'acid',
        'base',
        'activating-agent'
    ]
)

#: Prop  limit for ``Component`` ``component_type`` prop. One of 'reactor',
#: 'filter', 'separator', 'rotavap' or 'flask'.
COMPONENT_TYPE_PROP_LIMIT: PropLimit = PropLimit(
    enum=['reactor', 'filter', 'separator', 'rotavap', 'flask']
)

#: Pattern matching a float of value 100, e.g. '100', '100.0', '100.000' would
#: all be matched.
_hundred_float: str = r'(100(?:[.][0]+)?)'

#: Pattern matching any float between 10.000 and 99.999.
_ten_to_ninety_nine_float: str = r'([0-9][0-9](?:[.][0-9]+)?)'

#: Pattern matching any float between 0 and 9.999.
_zero_to_ten_float: str = r'([0-9](?:[.][0-9]+)?)'

#: Pattern matching float between 0 and 100. Used for percentages.
PERCENT_RANGE_PROP_LIMIT: PropLimit = PropLimit(
    r'^(' + _hundred_float + '|'\
        + _ten_to_ninety_nine_float + '|' + _zero_to_ten_float + ')$',
    hint='Expecting number from 0-100 representing a percentage, e.g. "50", "8.5".',
    default='0',
)
