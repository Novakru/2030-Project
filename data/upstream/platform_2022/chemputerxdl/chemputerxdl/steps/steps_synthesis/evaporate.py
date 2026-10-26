"""
.. module:: steps_synthesis.evaporate
    :platforms: Unix, Windows
    :synopsis: XDL step for evaporation of material form a vessel

"""

from typing import Optional, List, Dict, Any, Union
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import Step
from xdl.steps.templates import AbstractEvaporateStep
from xdl.utils.misc import SanityCheck
from xdl.utils.prop_limits import (
    TIME_PROP_LIMIT,
    TEMP_PROP_LIMIT,
    VOLUME_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    PRESSURE_PROP_LIMIT,
    PropLimit,
)
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from ..base_step import ChemputerStep
from ..steps_base import (
    CRotavapLiftDown,
    CRotavapAutoEvaporation,
    CRotavapStart,
    CRotavapStop,
    CTemperatureControllerSetTemp,
    CTemperatureControllerStart,
    CTemperatureControllerStop,
    CStirringControllerSetSpeed,
    CConnect,
    CR300RotavapSetAutoMode,
    CR300RotavapSetManualMode,
    CPressureControllerSetPressure,
    CR300RotavapStartChiller,
)
from ..steps_utility import (
    StopHeatChill,
    Wait,
    Purge,
    Transfer,
    StartVacuum,
    StopVacuum,
    RotavapStopEverything,
    HeatChillToTemp,
    StartStir,
    VentVacuum,
    StopStir,
    EvaporateDynamic,
)

from ...constants import (
    COLLECT_PORT, CHEMPUTER_WASTE, R300_ROTOVAP, ROTAVAP_CLASSES)
from ...utils.execution import (
    get_nearest_node,
    get_rotavap_collection_flask_volume,
    get_heater_chiller,
    get_vacuum_configuration)

class Evaporate(ChemputerStep, AbstractEvaporateStep):
    """Evaporate contents of given vessel at given temp and given pressure for
    given time.

    Args:
        vessel (str): Name of rotavap vessel.
        temp (float): Temperature to set rotavap water bath to in °C.
        pressure (float): Pressure to set rotavap vacuum to in mbar. Has no
            effect if mode == 'auto', otherwise must be passed.
        time (float): Time to rotavap for in seconds.
        stir_speed (float): Speed in RPM to rotate flask at.
        mode (str): 'manual' or 'auto'. If 'manual', given time/temp/pressure
            are used. If 'auto', automatic pressure/time evaluation built into
            the rotavap are used. In this case time and pressure should still be
            given, but correspond to maximum time and minimum pressure that if
            either is reached, the evaporation will stop.
    """

    DEFAULT_PROPS = {
        'time': '2 hrs',
        'stir_speed': '150 RPM',
        'pressure': None,
        'mode': 'manual',
        'temp': '25°C',
        'chiller_temp': '5 °C',
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'vessel_is_simple_flask': bool,
        'temp': float,
        'pressure': float,
        'time': float,
        'stir_speed': float,
        'mode': str,
        'waste_vessel': str,
        'collection_flask_waste_vessel': str,
        'collection_flask_volume': float,
        'chiller': str,
        'is_r300': bool,
        'inert_gas': str,
        'vacuum_source': str,
        'vacuum_device': str,
        'chiller_temp': float,
    }

    INTERNAL_PROPS = [
        'vessel_is_simple_flask',
        'waste_vessel',
        'collection_flask_waste_vessel',
        'collection_flask_volume',
        'chiller',
        'is_r300',
        'inert_gas',
        'vacuum_source',
        'vacuum_device'
    ]

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'chiller_temp': TEMP_PROP_LIMIT,
        'pressure': PRESSURE_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'mode': PropLimit(
            enum=['manual', 'auto', 'purge'],
            default='manual',
        ),
        'collection_flask_volume': VOLUME_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        temp: float = 'default',
        chiller_temp: float = 'default',
        pressure: Optional[float] = 'default',
        time: Optional[float] = 'default',
        stir_speed: Optional[float] = 'default',
        mode: Optional[str] = 'default',

        # Internal properties
        vessel_is_simple_flask: bool = False,
        waste_vessel: Optional[str] = None,
        collection_flask_waste_vessel: Optional[str] = None,
        collection_flask_volume: Optional[float] = None,
        chiller: bool = False,
        is_r300: bool = False,
        inert_gas: Optional[str] = None,
        vacuum_source: Optional[str] = None,
        vacuum_device: Optional[str] = None,
        **kwargs
    ):
        super().__init__(locals())

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=not self.is_r300 or self.mode in ['manual', 'auto'],
                error_msg=(f"The Buchi R300 rotavap '{self.vessel}' "
                           f"does not supprote the mode '{self.mode}'.")
            )]

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        # A rotary evaporator is availalbe for evaporation.
        if graph.nodes[self.vessel]["class"] in ROTAVAP_CLASSES:

            # Obtain collection volume form rotavap if not defined
            if not self.collection_flask_volume:
                self.collection_flask_volume =\
                    get_rotavap_collection_flask_volume(graph,
                                                        self.vessel)

            # Obtain waste vessel if not defined
            if not self.waste_vessel:
                self.waste_vessel = get_nearest_node(
                    graph, self.vessel, CHEMPUTER_WASTE
                )

                # Get collection flask waste vessel, not always the same as
                # evaporate port waste vessel.
                self.collection_flask_waste_vessel = get_nearest_node(
                    graph,
                    self.vessel,
                    CHEMPUTER_WASTE,
                    src_port=COLLECT_PORT
                )
        else:
            self.vessel_is_simple_flask = True
            # Get the vacuum configuration associated with the target flask.
            vacuum_info = get_vacuum_configuration(graph, self.vessel)
            if self.inert_gas is None:

                # No inert gas source has been provided to refill the flask
                # afer evaporation. Trying to find a suitable source.
                inert_gas_source = vacuum_info['valve_inert_gas']
                if inert_gas_source:
                    # There is at least one inert gas source available. Use the
                    # first one (not necessarily the closest).
                    self.inert_gas = inert_gas_source

            # Identify the vacuum source.
            if self.vacuum_source is None:
                self.vacuum_source = vacuum_info['source']

            # Identify the vacuum device.
            if self.vacuum_device is None:
                self.vacuum_device = vacuum_info['device']

        _, self.chiller = get_heater_chiller(graph, self.vessel)

        self.is_r300 = graph.nodes[self.vessel]['class'] == R300_ROTOVAP

    def get_chiller_steps_if_present(
        self, start: bool = True
    ) -> Optional[Step]:
        """Get chiller steps if a chiller is present. Chiller is for cooling
        the condensor so don't need to set temp, just start.

        Args:
            start (bool, optional): Start the chiller or stop. Defaults to True.

        Returns:
            Optional[Step]: Chiller step if present.
        """

        # Chiller is attached
        if self.chiller:
            if start:
                return [CTemperatureControllerSetTemp(self.chiller,
                                                      self.chiller_temp),
                        CTemperatureControllerStart(self.chiller)]
            else:
                return [CTemperatureControllerStop(self.chiller)]
        return []

    def get_default_steps(self, col_vol: Union[float, str]) -> List[Step]:
        """Get the list of default steps to execute for this Step.

        Args:
            col_vol (float): Collection volume

        Returns:
            List[Step]: Steps to execute
        """
        return (
            self.get_chiller_steps_if_present(start=True)
            + [
                # Set rotation speed
                CStirringControllerSetSpeed(
                    self.vessel, self.stir_speed),

                # Start
                CRotavapStart(self.vessel),

                # Wait for target temp to be reached.
                HeatChillToTemp(
                    self.vessel, self.temp, stir_speed=self.stir_speed),

                # Set pressure
                StartVacuum(
                    self.vessel, self.pressure),

                # Wait for evaporation to happen.
                Wait(time=self.time),

                # Stop evaporation.
                CRotavapStop(self.vessel),

                # Stop vacuum
                StopVacuum(
                    self.vessel,
                ),
                VentVacuum(
                    self.vessel
                )
            ]
            + self.get_chiller_steps_if_present(start=False)
            + [self.get_transfer_collect_to_waste_step(col_vol)]
        )

    def get_auto_steps(self, col_vol: Union[float, str]) -> List[Step]:
        """Get steps for automatic evaporation

        Args:
            col_vol (float): Collection volume

        Returns:
            List[Step]: Steps to execute
        """

        # Default presure
        pressure = 1  # 1 == auto pressure

        # Pressure already defined
        if self.pressure:
            # Approximation. Pressure given should be pressure solvent
            # evaporates at, but in auto evaporation, pressure is the limit
            # of the pressure ramp, so actual pressure given needs to be
            # lower.
            pressure = self.pressure / 2

        return (
            # Start rotation
            [StartStir(self.vessel, self.stir_speed)]
            # Lower flask into bath.
            + [CRotavapLiftDown(self.vessel)]
            # Start chiller if present
            + self.get_chiller_steps_if_present()
            # Start heating
            + [HeatChillToTemp(
                self.vessel, self.temp, stir_speed=self.stir_speed)]
            # Auto Evaporation
            + [CRotavapAutoEvaporation(
                rotavap_name=self.vessel,
                sensitivity=2,  # High sensitivity
                vacuum_limit=pressure,
                time_limit=self.time,
                vent_after=True
            )]
            # Stop evaporation.
            + [RotavapStopEverything(self.vessel)]
            # Stop chiller if present
            + self.get_chiller_steps_if_present(start=False)
            # Empty collect flask
            + [self.get_transfer_collect_to_waste_step(col_vol)]
        )

    def get_transfer_collect_to_waste_step(self, col_vol):
        """Transfer solvent collected in collection flask to waste."""
        return Transfer(
            from_vessel=self.vessel,
            to_vessel=self.waste_vessel,
            from_port=COLLECT_PORT,
            volume=col_vol,
            # Transfer is not quantitative or precise so no need to use
            # slow aspiration speed.
            aspiration_speed="40"
        )

    def get_purge_steps(self) -> List[Step]:
        """Get steps for ``mode='purge'``. Do evaporation by purging liquid with
        gas.
        """
        steps = []
        # If temp is not None or RT, add heating step.
        if not (self.temp is None or (18 <= self.temp <= 25)):
            steps.append(HeatChillToTemp(
                vessel=self.vessel,
                temp=self.temp,
            ))
        steps.append(
            Purge(
                vessel=self.vessel,
                time=self.time,
            )
        )
        if self.temp is not None:
            steps.append(StopHeatChill(vessel=self.vessel))
        return steps

    def get_steps_for_evaporation_in_flask(self) -> List[Step]:
        """Peform auto-evaporation in an arbitrary flask connected
        to a vacuum source capable of the auto mode.
        """
        # Default presure
        pressure = 1  # 1 == auto pressure

        # Pressure already defined
        if self.pressure:
            # Approximation. Pressure given should be pressure solvent
            # evaporates at, but in auto evaporation, pressure is the limit
            # of the pressure ramp, so actual pressure given needs to be
            # lower.
            pressure = self.pressure / 2

        # Define how to vent vacuum - with inert gas (if available)
        # or air (via the vacuum pump)
        if self.inert_gas is not None:
            vent_with_air = False
        else:
            vent_with_air = True

        steps = []

        # If temp is not None or RT, add heating step.
        if not (self.temp is None or (18 <= self.temp <= 25)):
            steps.append(
                HeatChillToTemp(
                    vessel=self.vessel,
                    temp=self.temp,
                    stir_speed=self.stir_speed,
                    stir=True
                )
            )
        else:
            steps.append(
                StartStir(
                    vessel=self.vessel,
                    stir_speed=self.stir_speed
                )
            )

        # Connect vessel to vacuum source
        steps.append(CConnect(self.vessel, self.vacuum_source))
        if self.mode == 'auto':
            # Evaporate in 'auto' mode
            steps.append(
                CRotavapAutoEvaporation(
                    rotavap_name=self.vacuum_source,
                    sensitivity=2,  # High sensitivity
                    vacuum_limit=pressure,
                    time_limit=self.time,
                    vent_after=vent_with_air
                )
            )
        elif self.mode == 'manual':
            pass
            # Start vacuum pump.
            steps.append(StartVacuum(self.vacuum_device, self.pressure))
            # Wait for evaporation to happen.
            steps.append(Wait(time=self.time))
            # Stop vacuum pump.
            steps.append(StopVacuum(self.vacuum_device))

        # Vent with inert gas if available
        if not vent_with_air:
            # Open connection to inert gas source.
            steps.append(CConnect(self.inert_gas, self.vessel))
            # Allow inert gas to flow for 60 s.
            steps.append(Wait(60))

        # Stop temperature control
        if self.temp is not None:
            steps.append(StopHeatChill(vessel=self.vessel))
        else:
            steps.append(StopStir(vessel=self.vessel))

        return steps

    def get_R300_steps(self, col_vol):
        """Get the list of default steps to execute for this Step.

        Args:
            col_vol (float): Collection volume

        Returns:
            List[Step]: Steps to execute
        """
        steps = []
        if self.mode == 'auto':
            steps.append(CR300RotavapSetAutoMode(self.vessel))
        elif self.mode == 'manual':
            steps.append(CR300RotavapSetManualMode(self.vessel))
            steps.append(CPressureControllerSetPressure(
                pressure_controller=self.vessel,
                pressure=self.pressure))
        # Set stir rate
        steps.append(CStirringControllerSetSpeed(self.vessel,
                                                 self.stir_speed))
        # Set chiller temperature and start chiller
        steps.append(CR300RotavapStartChiller(self.vessel,
                                              self.chiller_temp))
        # Set heating bath temperature and start heating
        steps.append(HeatChillToTemp(self.vessel,
                                     self.temp,
                                     stir_speed=self.stir_speed))
        # Send rotavap lift down
        steps.append(CRotavapLiftDown(self.vessel))
        # Start rotavap operation
        steps.append(CRotavapStart(self.vessel))
        if self.mode == 'auto':
            # Perform dynamic evaporation.
            # Use the given time as a hard limit for the process.
            steps.append(EvaporateDynamic(self.vessel, self.time))
        elif self.mode == 'manual':
            # Wait
            steps.append(Wait(self.time))
        # Stop evaporation process
        steps.append(CRotavapStop(self.vessel))
        # Stop temperature control in heating bath
        steps.append(StopHeatChill(self.vessel))
        # Empty collection flask
        steps.append(self.get_transfer_collect_to_waste_step(col_vol))

        return steps

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        # Define the colelction volume
        collection_flask_volume = 'all'

        # Collection volume defiend
        if self.collection_flask_volume:
            collection_flask_volume = self.collection_flask_volume

        if self.is_r300:
            steps = self.get_R300_steps(collection_flask_volume)
        else:
            # Auto evaporation mode
            if self.mode == "auto":
                if self.vessel_is_simple_flask:
                    steps = self.get_steps_for_evaporation_in_flask()
                else:
                    # Get automatic evaporation steps
                    steps = self.get_auto_steps(collection_flask_volume)

            # Purge mode
            elif self.mode == 'purge':
                steps = self.get_purge_steps()

            # Manual mode
            else:
                if self.vessel_is_simple_flask:
                    steps = self.get_steps_for_evaporation_in_flask()
                else:
                    # Get Default steps
                    steps = self.get_default_steps(collection_flask_volume)

        # Remove blanks
        steps = [step for step in steps if step is not None]
        return steps

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Get the requirements needed for this step

        Returns:
            Dict[str, Dict[str, Any]]: Step requirements
        """

        # Temp is defined and above 25, require heat chill
        heatchill = True if self.temp and self.temp > 25 else False

        # Define requires temperatures
        temps = []
        if self.temp:
            temps = [self.temp]

        # Return requirements
        return {
            'vessel': {
                'rotavap': True,
                'heatchill': heatchill,
                'temp': temps,
            }
        }
