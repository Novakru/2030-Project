"""
This file contains all constants used in the Chempiler project,
such as dictionary keys, device types, and so forth. Keeping them
all in one file makes future maintenance a lot easier and avoids duplicates.
"""
from typing import Dict, List

# Pump speeds
#: Initial withdrawal pump speed
DEFAULT_INITIAL_PUMP_SPEED = 40
#: Final dispense pump speed
DEFAULT_END_PUMP_SPEED = 40
#: All other pump speeds
DEFAULT_MID_PUMP_SPEED = 40

#: Time in seconds to wait for after aspiration in order to allow pressure to
#: equalize.
AFTER_ASPIRATION_WAIT = 2

#: Pressure in mbar to count as atmospheric pressure when venting vacuum
ATMOSPHERIC_PRESSURE = 900

#: When cooling to a given temp only force cooling to `target_temp` plus this
#: value. Unit: degrees celsius.
COOLING_THRESHOLD = 0.5

#: Excess to remove during phrase separation to account for dead volume of
#: tubing.
SEPARATION_DEAD_VOLUME = 2.5

#: Pump speed to use for withdrawing during separation in mL / min.
SEPARATION_DEFAULT_INITIAL_PUMP_SPEED = 10

#: Pump speed to use for middle pump movements during separation in mL / min.
SEPARATION_DEFAULT_MID_PUMP_SPEED = 40

#: Pump speed to use for dispensing during separation in mL / min.
SEPARATION_DEFAULT_END_PUMP_SPEED = 40

#: Volume to prime conductivity sensor with during phase separation
SEPARATION_DEFAULT_PRIMING_VOLUME = 2

#: When doing ``c.move(...volume='all')``, calculate volume to move as
#: ``max(MOVE_ALL_MIN_EXCESS, current_volume * MOVE_ALL_EXCESS_FACTOR)``
MOVE_ALL_MIN_EXCESS: int = 5  # mL
MOVE_ALL_EXCESS_FACTOR: float = 0.1

# Class names
CHEMPUTER_FILTER: str = 'ChemputerFilter'
CHEMPUTER_REACTOR: str = 'ChemputerReactor'
CHEMPUTER_CARTRIDGE: str = 'ChemputerCartridge'
CHEMPUTER_WASTE: str = 'ChemputerWaste'
CHEMPUTER_FLASK: str = 'ChemputerFlask'
CHEMPUTER_VACUUM: str = 'ChemputerVacuum'
CHEMPUTER_SEPARATOR: str = 'ChemputerSeparator'
CHEMPUTER_VALVE: str = 'ChemputerValve'
CHEMPUTER_PUMP: str = 'ChemputerPump'
CHEMPUTER_MANIFOLD: str = 'ChemputerManifold'

JULABO_CF41: str = 'CF41Chiller'
HUBER_PETITE_FLEUR: str = 'PetiteFleurChiller'
IKA_RCT_DIGITAL: str = 'RCTDigitalHotplate'
IKA_RET_CONTROL_VISC: str = 'RETControlViscHotplate'
IKA_RV_10: str = "RV10Rotovap"
CVC3000: str = "CVC3000VacuumPump"
IKA_MICROSTAR_75: str = "Microstar75Stirrer"
RZR_2052: str = "RZR2052ControlStirrer"
HEIDOLPH_TORQUE_100: str = 'HeiTorque100PrecisionStirrer'
BUCHI_R300: str = 'R300Rotovap'

CHILLER_CLASSES: List[str] = [JULABO_CF41, HUBER_PETITE_FLEUR]
ROTAVAP_CLASSES: List[str] = [BUCHI_R300, IKA_RV_10]

#: Internal temp sensor keyword in graph temp_sensor property
INTERNAL_TEMP_SENSOR: str = 'internal'
#: External temp sensor keyword in graph temp_sensor property
EXTERNAL_TEMP_SENSOR: str = 'external'

# Assumption of Chempiler. Port that pump will be connected to valve.
PUMP_PORT: int = -1

#: Valid classes for a path to go through. Other classes can be included in a
#: a path must be given explicitly as through nodes.
VALID_THROUGH_CLASSES: List[str] = [CHEMPUTER_MANIFOLD, CHEMPUTER_VALVE]

#: Valid edge ports for different devices in graph.
VALID_PORTS: Dict[str, List[str]] = {
    'ChemputerSeparator': ['top', 'bottom'],
    'ChemputerReactor': [0, 1, 2],
    'ChemputerFilter': ['top', 'bottom'],
    'ChemputerPump': [0],
    'RV10Rotovap': ['evaporate', 'collect'],
    'R300Rotovap': ['evaporate', 'collect'],
    'ChemputerValve': [-1, 0, 1, 2, 3, 4, 5],
    'ChemputerFlask': [0],
    'ChemputerWaste': [0],
    'CommanduinoLabware': [0],
    'ChemputerCartridge': ['in', 'out']
}

#: Default edge ports for different devices in graph.
DEFAULT_PORTS: Dict[str, Dict[str, str]] = {
    'ChemputerSeparator': {'src': 'bottom', 'dest': 'bottom'},
    'ChemputerReactor': {'src': 0, 'dest': 0},
    'ChemputerFilter': {'src': 'bottom', 'dest': 'top'},
    'ChemputerPump': {'src': 0, 'dest': 0},
    'RV10Rotovap': {'src': 'evaporate', 'dest': 'evaporate'},
    'R300Rotovap': {'src': 'evaporate', 'dest': 'evaporate'},
    'ChemputerFlask': {'src': 0, 'dest': 0},
    'ChemputerWaste': {'src': 0, 'dest': 0},
    'CommanduinoLabware': {'src': 0, 'dest': 0}
}

#: Default ports for connecting nodes in graph, if ports not explicitly
#: specified.
DEFAULT_CONNECT_PORTS: Dict[str, Dict[str, str]] = {
    'ChemputerSeparator': {'src': 'bottom', 'dest': 'bottom'},
    'ChemputerReactor': {'src': 0, 'dest': 0},
    'ChemputerFilter': {'src': 'bottom', 'dest': 'bottom'},
    'ChemputerPump': {'src': 0, 'dest': 0},
    'RV10Rotovap': {'src': 'evaporate', 'dest': 'evaporate'},
    'R300Rotovap': {'src': 'evaporate', 'dest': 'evaporate'},
    'ChemputerFlask': {'src': 0, 'dest': 0},
    'ChemputerWaste': {'src': 0, 'dest': 0},
    'CommanduinoLabware': {'src': 0, 'dest': 0}
}

#: Synonyms for inert gas, used for knowing which movements to track with
#: volume tracking.
INERT_GAS_NAMES: List[str] = ['n2', 'nitrogen', 'ar', 'argon']
