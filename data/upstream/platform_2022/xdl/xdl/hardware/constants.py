from typing import List

# These lists are here so that generic names like 'rotavap' can be used
# in XDL, and specific names like 'IKARV10' can be used in the graph
# and the XDLExecutor will still know that it can map a component with
# type 'rotavap' to a component with type 'IKARV10'.
REACTOR_TYPES: List[str] = ['reactor', 'ChemputerReactor']
FILTER_TYPES: List[str] = ['filter', 'ChemputerFilter']
SEPARATOR_TYPES: List[str] = ['separator', 'ChemputerSeparator']
ROTAVAP_TYPES: List[str] = ['rotavap', 'RV10Rotovap', 'R300Rotovap']
FLASK_TYPES: List[str] = ['flask', 'ChemputerFlask']
WASTE_TYPES: List[str] = ['waste', 'ChemputerWaste']
CARTRIDGE_TYPES: List[str] = ['cartridge', 'ChemputerCartridge']
