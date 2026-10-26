"""
Device classes from other packages. Re-exporting them here allows
capabilities to be overridden and means SerialLabware can be accessed through
ChemputerAPI.
"""

import logging
from typing import List, Tuple

import SerialLabware
from SerialLabware import *
from .flasks import ChemputerFlask

# Get the SerialLabware logger
logging.getLogger("SerialLabware").setLevel(logging.DEBUG)

# Remove some device classes from namespaces
# so they can be overloaded.
for device_class_name in ['RV10Rotovap']:
    del(globals()[device_class_name])

# IKA RV10 Rotavap
ikarv10_capabilities = [
    ('source', 'evaporate'), ('sink', 'evaporate'), ('source', 'collect')]

class RV10Rotovap(SerialLabware.RV10Rotovap, ChemputerFlask):
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    def __init__(
        self,
        port=None,
        connection_mode=None,
        device_name=None,
        address=None,
        *args, **kwargs
    ):
        ChemputerFlask.__init__(self, *args, **kwargs)
        SerialLabware.RV10Rotovap.__init__(
            self,
            port=port,
            device_name=device_name,
            address=address,
            connection_mode=connection_mode,
        )

    @property
    def capabilities(self):
        return ikarv10_capabilities
