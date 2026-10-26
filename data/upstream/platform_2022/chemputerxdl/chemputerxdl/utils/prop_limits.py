"""
.. module:: utils.prop_limits
    :platforms: Unix, Windows
    :synopsis: Limit objects to check the ranges of certain properties in
                XDL steps

"""

from xdl.utils.prop_limits import PropLimit
from ..constants import (
    IKA_RV_10,
    JULABO_CF41,
    HUBER_PETITE_FLEUR,
    HEIDOLPH_TORQUE_100,
    IKA_RCT_DIGITAL,
    IKA_RET_CONTROL_VISC,
    IKA_MICROSTAR_75,
    CVC3000,
    RZR_2052,
    CHEMPUTER_WASTE,
    CHEMPUTER_FILTER,
    CHEMPUTER_REACTOR,
    CHEMPUTER_FLASK,
    CHEMPUTER_PUMP,
    CHEMPUTER_VALVE,
    CHEMPUTER_VACUUM,
    CHEMPUTER_CARTRIDGE,
    CHEMPUTER_SEPARATOR,
    INTERNAL_TEMP_PROBE,
    EXTERNAL_TEMP_PROBE,
)

# Limits for the Valve ports
# -1, 1, 2, 3, 4, 5
VALVE_PORT_PROP_LIMIT = PropLimit(
    enum=['0', '1', '2', '3', '4', '5'],
    default='0',
)

# Limits for the Pneumatic Controller ports
PNEUMATIC_CONTROLLER_PORT_PROP_LIMIT = PropLimit(
    enum=['1', '2', '3', '4', '5', '6'],
    default='1',
)

PNEUMATIC_CONTROLLER_PRESSURE_PROP_LIMIT = PropLimit(
    enum=['low', 'high'],
    default='low'
)

# Limits for the different types of port supported
# -1, 1, 2, 3, 4, 5, top, bottom, evaporate, collect, in, out
PORT_PROP_LIMIT = PropLimit(

    enum=[
        '0', '1', '2', '3', '4', '5', 'top', 'bottom', 'evaporate',
        'collect', 'in', 'out'
    ],
    default='0',
)

# Limits for the vessel types
VESSEL_TYPE_PROP_LIMIT = PropLimit(
    enum=['filter', 'reactor', 'separator', 'rotavap', 'flask']
)

# Limits for the vessel classes
VESSEL_CLASS_PROP_LIMIT = PropLimit(
    enum=[
        CHEMPUTER_FILTER, CHEMPUTER_REACTOR, CHEMPUTER_PUMP,
        CHEMPUTER_VALVE, CHEMPUTER_SEPARATOR, CHEMPUTER_FLASK,
        CHEMPUTER_WASTE, CHEMPUTER_VACUUM, CHEMPUTER_CARTRIDGE,
        JULABO_CF41, HUBER_PETITE_FLEUR, IKA_RET_CONTROL_VISC,
        IKA_RV_10, CVC3000, IKA_MICROSTAR_75, RZR_2052, HEIDOLPH_TORQUE_100,
        IKA_RCT_DIGITAL,
    ],
)

# Limits for int (unsigned char)
INT_0_255_PROP_LIMIT = PropLimit(
    r'^(2[0-5][0-5]|1[0-9][0-9]|[0-9]?[0-9])$',
    hint='Expecting int from 0-255, e.g. "128".',
    default='0',
)

# Temperature sensor for reading temperature of hotplate or chiller
TEMP_SENSOR_PROP_LIMIT: PropLimit = PropLimit(
    enum=[INTERNAL_TEMP_PROBE, EXTERNAL_TEMP_PROBE])

# Code passed to serial labware to specify internal or external probe of
# hotplate or chiller.
TEMP_SENSOR_CODE_PROP_LIMIT: PropLimit = PropLimit(enum=['0', '1'])

# Sensor reading data, may be ANY float, including -inf, inf, nan
SENSOR_READING_LIMIT: PropLimit = PropLimit(
    r'^([-]?inf|nan|[-]?[0-9]*(?:[.][0-9]+)?)$',
    hint='Any value that can be converted to float',
    default='42',
)

# Odd integers
ODD_INTS: PropLimit = PropLimit(
    r'^\d*[13579]$',
    hint='Any odd integer',
    default='7',
)

# Filtering functions for the sensor readings
FILTERING_FUNCTIONS_LIMIT: PropLimit = PropLimit(
    enum=['median', 'fft']
)

# Sensor data readings trend
SENSOR_DATA_TREND_LIMIT: PropLimit = PropLimit(
    enum=[
        'ascending',
        'descending',
    ]
)
