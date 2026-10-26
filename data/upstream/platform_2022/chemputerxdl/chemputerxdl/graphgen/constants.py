"""
..module:: graphgen.constants
    :platforms: Unix, Windows
    :synopsis: Constants used within the graphgen module

"""

from ..constants import (
    IKA_RV_10, JULABO_CF41, IKA_RCT_DIGITAL, HUBER_PETITE_FLEUR)

# Fixable issues
HEATER_CHILLER_TEMP_RANGES = {
    JULABO_CF41: (-40, 100),
    # https://www.wilmad-labglass.com/uploadedFiles/Main_Site/Content/Literature_Center/RV10_WEB.pdf # noqa: E501
    IKA_RV_10: (18, 180),
    # https://www.ika.com/en/Products-Lab-Eq/Magnetic-Stirrers-Hot-Plate-Lab-Mixer-Stirrer-Blender-csp-188/RCT-basic-cpdt-3810000/ # noqa: E501
    IKA_RCT_DIGITAL: (18, 360),
    HUBER_PETITE_FLEUR: (-40, 100),
}

REMOVE_SRC_PORT = 'remove_src_port'
REMOVE_DEST_PORT = 'remove_dest_port'
SRC_PORT_INVALID = 'src_port_invalid'
DEST_PORT_INVALID = 'dest_port_invalid'
SWITCH_TO_IN_EDGE = 'switch_to_in_edge'
SWITCH_TO_OUT_EDGE = 'switch_to_out_edge'
ADD_CHILLER_TO_REACTOR = 'add_chiller_to_reactor'
NOT_ENOUGH_SPARE_PORTS = 'not_enough_spare_ports'

# Errors
INVALID_PORT_ERROR = 'invalid_port_error'
MISSING_COMPONENT_TYPE_ERROR = 'missing_component_type_error'
MISSING_HEATER_OR_CHILLER_ERROR = 'missing_heater_or_chiller_error'
CANNOT_REACH_TARGET_TEMP_ERROR = 'cannot_reach_target_temp_error'

# Graph
GRIDSIZE = 40

# Misc
DEFAULT_BUFFER_FLASK_VOLUME: int = 500  # mL
DEFAULT_REAGENT_FLASK_VOLUME: int = 100  # mL
HEATER_CHILLER_TEMP_RANGES = {
    JULABO_CF41: (-40, 140),
    # https://www.wilmad-labglass.com/uploadedFiles/Main_Site/Content/Literature_Center/RV10_WEB.pdf # noqa: E501
    IKA_RV_10: (18, 180),
    # https://www.ika.com/en/Products-Lab-Eq/Magnetic-Stirrers-Hot-Plate-Lab-Mixer-Stirrer-Blender-csp-188/RCT-basic-cpdt-3810000/ # noqa: E501
    IKA_RCT_DIGITAL: (18, 360),
    HUBER_PETITE_FLEUR: (-40, 100),
}
DEFAULT_CHILLER_DATA = {
    "id": "chiller",
    "type": "chiller",
    "x": -40,
    "y": 320,
    "internalId": 3,
    "label": "chiller",
    "class": "JULABOCF41",
    "name": "chiller",
    "min_temp": None,
    "max_temp": None,
    "port": "",
    "address": "",
    "mode": "ethernet"
}
