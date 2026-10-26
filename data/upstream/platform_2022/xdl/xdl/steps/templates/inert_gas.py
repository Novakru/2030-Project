from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE
from ...utils.prop_limits import TIME_PROP_LIMIT, PRESSURE_PROP_LIMIT
from ...utils.vessels import VesselSpec

class AbstractEvacuateAndRefillStep(AbstractXDLElementTemplate, AbstractStep):
    """Evacuate vessel and refill with inert gas.

    Name: Evacuate

    Mandatory props:
        vessel (vessel): Vessel to evacuate and refill.
        gas (str): Gas to refill vessel with. If not given use any available
            inert gas.
        repeats (int): Number of evacuation/refill cycles to perform.
    """
    MANDATORY_NAME = 'EvacuateAndRefill'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'gas': str,
        'repeats': int,
    }

    MANDATORY_DEFAULT_PROPS = {
        'gas': None,
        'repeats': None,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(inert_gas=self.gas is None, vacuum=True),
        }

class AbstractPurgeStep(AbstractXDLElementTemplate, AbstractStep):
    """Purge liquid by bubbling gas through it.

    Name: Purge

    Mandatory props:
        vessel (vessel): Vessel containing liquid to purge with gas.
        gas (str): Gas to purge vessel with. If not given use any available
            inert gas.
        time (float): Optional. Time to bubble gas through vessel.
        pressure (float): Optional. Pressure of gas.
        flow_rate (float): Optional. Flow rate of gas in mL / min.
    """
    MANDATORY_NAME = 'Purge'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'time': float,
        'gas': str,
        'pressure': float,
        'flow_rate': float,
    }

    MANDATORY_DEFAULT_PROPS = {
        'time': None,
        'gas': None,
        'pressure': None,
        'flow_rate': None,
    }

    MANDATORY_PROP_LIMITS = {
        'time': TIME_PROP_LIMIT,
        'pressure': PRESSURE_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(inert_gas=self.gas is None),
        }

class AbstractStartPurgeStep(AbstractXDLElementTemplate, AbstractStep):
    """Start purging liquid by bubbling gas through it.

    Name: Start Purge

    Mandatory props:
        vessel (vessel): Vessel containing liquid to purge with gas.
        gas (str): Gas to purge vessel with. If not given use any available
            inert gas.
        pressure (float): Optional. Pressure of gas.
        flow_rate (float): Optional. Flow rate of gas in mL / min.
    """
    MANDATORY_NAME = 'StartPurge'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'pressure': float,
        'flow_rate': float,
        'gas': str,
    }

    MANDATORY_DEFAULT_PROPS = {
        'gas': None,
        'pressure': None,
        'flow_rate': None,
    }

    MANDATORY_PROP_LIMITS = {
        'pressure': PRESSURE_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(inert_gas=self.gas is None),
        }

class AbstractStopPurgeStep(AbstractXDLElementTemplate, AbstractStep):
    """Stop bubbling gas through vessel.

    Name: Stop Purge

    Mandatory props:
        vessel (vessel): Vessel to stop bubbling gas through.
    """
    MANDATORY_NAME = 'StopPurge'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(),
        }
