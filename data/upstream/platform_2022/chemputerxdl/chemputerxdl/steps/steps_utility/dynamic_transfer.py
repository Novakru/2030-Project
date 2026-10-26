"""
    XDL step to dynamically transfer liquid and monitor the process with the
        bubble sensor.
"""
# disabling annoying messages
# pylint: disable=unused-argument, attribute-defined-outside-init

# std lib
from typing import Optional, List
from enum import IntEnum

# external
from networkx import MultiDiGraph
import numpy as np

# XDL
from xdl.steps.base_steps import AbstractDynamicStep, Step
from xdl.steps.special_steps import Repeat
from xdl.utils.prop_limits import (
    VOLUME_PROP_LIMIT,
    TIME_PROP_LIMIT,
)
from xdl.utils.misc import SanityCheck
from xdl.constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE

# relative
from ..base_step import ChemputerStep
from .heatchill import StopHeatChill
from .stirring import StopStir
from .liquid_handling import FlushTubing
from ..steps_base import CMove, GetSensorReadings, SetSensor
from ...utils.prop_limits import PORT_PROP_LIMIT
from ...constants import (
    PORT_PROP_TYPE,
    DEFAULT_PORTS,
    DEFAULT_VISCOUS_ASPIRATION_SPEED,
)
from ...utils.execution import (
    get_reagent_vessel,
    get_cartridge,
    get_vessel_stirrer,
    node_in_graph,
    get_heater_chiller,
    get_aspiration_pump,
    get_pump_max_volume,
    get_bubble_sensor,
)

# Fraction of "bubble" readings to make decisions
OKAY_THRESHOLD = .2
NOT_OKAY_THRESHOLD = .5
ERROR_THRESHOLD = .8

# Threshold of the bubble sensor reading
# Air gaps - below, any liquid - above
BUBBLE_THRESHOLD = 420

# Default name of the bubble reading
BUBBLE_SENSOR_READING = 'bubbles'


class DynamicTransfer(ChemputerStep, AbstractDynamicStep):
    """
    Dynamically transfer the liquid using feedback from bubble sensor.

    Basically a copy-paste of normal Transfer step, except for core CMove,
        which is run dynamically, using a feedback from the bubble sensor.

    Args:
        from_vessel (str): Vessel name to transfer from.
        to_vessel (str): Vessel name to transfer to.
        volume (float): Volume to transfer in mL.
        from_port (str): Port on from_vessel to transfer from.
        to_port (str): Port on to_vessel to transfer from.
        through (str): Node name to transfer to.
        aspiration_speed (float): Speed in mL / min to pull liquid out of
            from_vessel.
        move_speed (float): Speed in mL / min to move liquid at.
        dispense_speed (float): Speed in mL / min to push liquid out of pump
            into to_vessel.
        rinse_withdrawal_excess (Optional[float]): specifies % excess volume to
            be aspirated after rinse steps. Expressed as a decimal fraction in
            range 0 -> 1. Defaults to 0.2 (i.e. 20 % excess).
        through_cartridge (str): Internal property. Cartridge to pass through.
    """

    DEFAULT_PROPS = {
        'aspiration_speed': 10,  # mL / min
        'dispense_speed': 40,  # mL / min
        'move_speed': 40,  # mL / min
        'viscous': False,
        'flush_tubing': False,
        'from_port': None,
        'to_port': None,
        'through': None,
        'time': None,
        'rinsing_solvent': None,
        'rinsing_volume': None,
        'rinsing_repeats': 1,
        'rinse_withdrawal_excess': 0.2,
        'volume_window': 5,
    }

    INTERNAL_PROPS = [
        'through_cartridge',
        'transfer_all',
        'from_vessel_has_stirrer',
        'from_vessel_has_heater',
        'from_vessel_has_chiller',
        'rinsing_solvent_vessel',
        'aspiration_pump',
        'aspiration_pump_max_volume',
        'bubble_sensor',
    ]

    PROP_TYPES = {
        'from_vessel': VESSEL_PROP_TYPE,
        'to_vessel': VESSEL_PROP_TYPE,
        'volume': float,
        'from_port': PORT_PROP_TYPE,
        'to_port': PORT_PROP_TYPE,
        'through': str,
        'time': float,
        'aspiration_speed': float,
        'move_speed': float,
        'dispense_speed': float,
        'viscous': bool,
        'through_cartridge': str,
        'transfer_all': bool,
        'from_vessel_has_stirrer': bool,
        'from_vessel_has_heater': bool,
        'from_vessel_has_chiller': bool,
        'flush_tubing': bool,
        'rinsing_solvent': REAGENT_PROP_TYPE,
        'rinsing_volume': float,
        'rinsing_repeats': int,
        'rinsing_solvent_vessel': str,
        'rinse_withdrawal_excess': float,
        'aspiration_pump': str,
        'aspiration_pump_max_volume': float,
        'volume_window': float,
        'bubble_sensor': str,
    }

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'from_port': PORT_PROP_LIMIT,
        'to_port': PORT_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'rinsing_volume': VOLUME_PROP_LIMIT,
    }

    # continue codes
    ContinueCode = IntEnum('ContinueCode',
                           'OKAY NOT_OKAY ERROR EMPTY NO_BUBBLE_SENSOR')

    def __init__(
            self,
            from_vessel: str,
            to_vessel: str,
            volume: float,
            rinsing_solvent: Optional[str] = 'default',
            rinsing_volume: Optional[float] = 'default',
            rinsing_repeats: Optional[int] = 'default',
            from_port: Optional[str] = 'default',
            to_port: Optional[str] = 'default',
            through: Optional[str] = 'default',
            time: Optional[float] = 'default',
            aspiration_speed: Optional[float] = 'default',
            move_speed: Optional[float] = 'default',
            dispense_speed: Optional[float] = 'default',
            viscous: Optional[bool] = 'default',
            flush_tubing: Optional[bool] = 'default',
            rinse_withdrawal_excess: Optional[float] = 'default',
            volume_window: Optional[float] = 'default',

            # Internal properties
            through_cartridge: Optional[str] = None,
            transfer_all: Optional[bool] = False,
            from_vessel_has_stirrer: Optional[bool] = False,
            from_vessel_has_heater: Optional[bool] = None,
            from_vessel_has_chiller: Optional[bool] = None,
            rinsing_solvent_vessel: Optional[str] = None,
            aspiration_pump: Optional[str] = None,
            aspiration_pump_max_volume: Optional[float] = None,
            bubble_sensor: Optional[str] = None,
            **kwargs
    ) -> None:
        super().__init__(locals())

        self.continue_options = {
            self.ContinueCode.OKAY: self.continue_if_okay,
            self.ContinueCode.NOT_OKAY: self.continue_if_not_okay,
            self.ContinueCode.ERROR: self.continue_if_error,
            self.ContinueCode.EMPTY: self.continue_if_empty,
            self.ContinueCode.NO_BUBBLE_SENSOR: self.continue_if_no_bubble_sensor,  # noqa: E501
        }

        self.reset()

    def reset(self) -> None:
        """ Reset all internal variables, calculated during transfer. """
        self.total_transferred = 0  # Total volume transferred during operation
        self.readings = None  # Bubble sensor readings
        self.pump_current_volume = 0  # Current volume in aspiration pump
        self.volume_to_transfer = 0  # Current volume beeing transferred
        self.last_timestamp = 0

    def withdraw(self):
        """ Returns steps if more liquid needs to be withdrawn. """

        withdraw_steps = []

        withdraw_steps.extend([
            # Setting the new reading interval
            SetSensor(
                sensor=self.bubble_sensor,
                start=True,
                reading_interval=.1,
                on_finish=self.on_bubble_sensor_set,
            ),
            # Moving to aspiration pump
            CMove(
                from_vessel=self.from_vessel,
                from_port=self.from_port,
                to_vessel=self.aspiration_pump,
                volume=self.volume_to_transfer,
                aspiration_speed=self.aspiration_speed,
                move_speed=self.move_speed,
                dispense_speed=self.dispense_speed
            ),
            # Obtaining the readings
            GetSensorReadings(
                sensor=self.bubble_sensor,
                reading=BUBBLE_SENSOR_READING,
                from_timestamp=self.last_timestamp,
                on_reading=self.on_bubble_sensor_readings,
            ),
            # Resetting the reading interval
            SetSensor(
                sensor=self.bubble_sensor,
                start=False,
            ),
        ])

        # Updating current pump volume, assuming that it's been filled
        self.pump_current_volume += self.volume_to_transfer

        return withdraw_steps

    def transfer_to_vessel(self) -> List[Step]:
        """ Return steps needed to transfer from pump to target vessel. """

        self.logger.debug('Transferring to target vessel')

        # Emptying syringe
        steps_to_transfer = [
            CMove(
                from_vessel=self.aspiration_pump,
                to_vessel=self.to_vessel,
                to_port=self.to_port,
                volume=self.pump_current_volume,
                through=self.through_cartridge,
                aspiration_speed=self.move_speed,
                move_speed=self.move_speed,
                dispense_speed=self.dispense_speed
            )
        ]

        # Reset counter
        self.pump_current_volume = 0

        return steps_to_transfer

    def on_bubble_sensor_set(self, timestamp: float) -> None:
        """Callback function to record the timestamp when the bubble sensor
            background reading setting was changed.

        Args:
            timestamp (float): Timestamp when the background reading thread
                was changed. Used for readings indexing.
        """

        self.last_timestamp = timestamp

    def on_bubble_sensor_readings(self, readings: List) -> None:
        """ Callback function to update sensor readings when obtained.

        Updates internal readings and calls for analysis.
        """

        # Updating class placeholder
        self.readings = readings
        self.analyze()

    def continue_if_no_bubble_sensor(self) -> List:
        """ Returns steps to continue if no bubble sensor is found attached
        to the aspiration pump.

        Just return main move steps and update total transferred volume.
        """

        self.total_transferred = self.volume

        # Setting continue option to okay, so that subsequent call will
        # Return empty list due to all volume transferred
        self.continue_option = self.ContinueCode.OKAY

        return self.get_move_steps()

    def continue_if_okay(self) -> List:
        """ Returns further steps if previous were okay. """

        self.logger.info('Bubble sensor readings analysis: OKAY')
        # Updating continue option
        self.continue_option = self.ContinueCode.OKAY

        # First check versus current pump volume
        if self.pump_current_volume >= self.volume:
            self.logger.debug('Syring is full, transferring to target')
            # All volume in the syringe, go directly to transfer
            return self.transfer_to_vessel()

        # Then check if syringe is empty and everything's been transferred
        if (self.total_transferred == self.volume
                and self.pump_current_volume == 0):
            return []

        # Everything's been transferred, but still in the syringe
        if (self.total_transferred == self.volume
                and self.pump_current_volume != 0):
            return self.transfer_to_vessel()

        # Calculating volume to move
        # If leftover is less than window size
        if self.volume - self.total_transferred >= self.volume_window:
            self.volume_to_transfer = self.volume_window
        # Else transfer the reminder
        else:
            self.volume_to_transfer = self.volume % self.volume_window

        self.logger.debug('Calculated volume to transfer: %.2f',
                          self.volume_to_transfer)

        # More liquid left to transfer and syringe is full
        if (self.aspiration_pump_max_volume - self.pump_current_volume
                <= self.volume_to_transfer):
            return self.transfer_to_vessel()

        # Otherwise more liquid left to transfer, but syringe is not full yet
        # Continue withdrawing
        return self.withdraw()

    def continue_if_not_okay(self) -> List:
        """ Returns further steps if previous were not okay. """
        self.logger.info('Bubble sensor readings analysis: NOT OKAY')

        return self.continue_if_okay()

    def continue_if_error(self) -> List:
        """ Returns further steps if an error encountered in previous. """
        self.logger.info('Bubble sensor readings analysis: ERROR')

        return self.continue_if_okay()

    def continue_if_empty(self) -> List:
        """ Returns further steps if previous withdrawal considered empty. """
        self.logger.info('Bubble sensor readings analysis: EMPTY')

        return self.continue_if_okay()

    def analyze(self) -> List:
        """ Updates continue status based on the sensor reading analysis. """

        # Updating total volume when the move steps have been actually executed
        # In the future, these updates might change and go to the corresponding
        # Continue methods, depending on the analysis results.
        self.total_transferred += self.volume_to_transfer
        self.logger.info('Transferred to syringe %.2f; total transferred\
volume: %.2f', self.pump_current_volume, self.total_transferred)

        # Analyzing
        try:
            threshold_mask = self.readings < BUBBLE_THRESHOLD
        except TypeError:
            # Array with None -> simulation
            threshold_mask = np.array([1])

        # Portion of "bubble" readings
        bubble_readings_fraction = np.sum(threshold_mask) / len(self.readings)
        self.logger.info('Total bubble fraction current step: %.2f',
                         bubble_readings_fraction)

        # Making decisions
        if bubble_readings_fraction < OKAY_THRESHOLD:
            # Everything's okay
            self.continue_option = self.ContinueCode.OKAY
        elif bubble_readings_fraction < NOT_OKAY_THRESHOLD:
            # Light problems
            self.continue_option = self.ContinueCode.NOT_OKAY
        elif bubble_readings_fraction < ERROR_THRESHOLD:
            # More than half is empty
            self.continue_option = self.ContinueCode.ERROR
        else:
            # Moved "air"
            self.continue_option = self.ContinueCode.EMPTY

        # Reseting readings
        self.readings = []

    def on_start(self) -> List[Step]:
        """ Initial preparation steps.

        Stop stirring and initial withdrawal step.
        """

        return self.get_stop_stir_steps()

    def on_continue(self) -> List[Step]:
        """ Dynamically transfer from source to target.

        Transfer to first pump in a liquid path, check readings of the bubble
            sensor, decide on next steps.
        """
        return self.continue_options[self.continue_option]()

    def on_finish(self) -> List[Step]:
        """ Additional steps, that not need dynamic feedback.

        Flush the tubes, rinse if needed, stop heat-chill if needed.
        """
        return (
            self.get_flush_tubing_steps()
            + self.get_rinse_steps()
            + self.get_stop_heatchill_steps()
        )

    def get_simulation_steps(self) -> List[Step]:
        """ In simulation just run as normal transfer.
        """
        return (
            self.get_stop_stir_steps()
            + self.get_move_steps()
            + self.get_flush_tubing_steps()
            + self.get_rinse_steps()
            + self.get_stop_heatchill_steps()
        )

    def on_prepare_for_execution(self, graph: MultiDiGraph) -> str:
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for execution.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        if self.volume == 'all':
            self.transfer_all = True
            # Replacing volume with vessel's max volume
            # To avoid relaying on chempiler's volume calculation
            # And keep all internal counts properly updated
            self.volume = graph.nodes[self.from_vessel]['max_volume']

        # Obtain the through cartridge if not defined
        if not self.through_cartridge and self.through:
            self.through_cartridge = get_cartridge(graph, self.through)

        # Obtain the to port if not defined
        if self.to_port in [None, ''] and self.to_vessel:
            # Get the vessel class of the to_vessel
            to_class = graph.nodes[self.to_vessel]['class']

            # Ports are present in default ports, set them
            if to_class in DEFAULT_PORTS:
                self.to_port = DEFAULT_PORTS[to_class]['to']

        # Check if the from vessel has a stirrer attached
        self.from_vessel_has_stirrer = (
            True if get_vessel_stirrer(graph, self.from_vessel) else False
        )

        # From vessel is defined
        if self.from_vessel:
            # Get the vessel class from the graph
            from_class = graph.nodes[self.from_vessel]['class']

            # Get the ports if not defined
            if self.from_port in [None, ''] and self.from_vessel:
                # Vessel class is present in default ports, set it
                if from_class in DEFAULT_PORTS:
                    self.from_port = DEFAULT_PORTS[from_class]['from']

            # Get the aspiration pump and its maximum volume
            self.aspiration_pump = get_aspiration_pump(
                graph=graph,
                src_vessel=self.from_vessel,
                src_port=self.from_port
            )
            self.aspiration_pump_max_volume = get_pump_max_volume(
                graph,
                self.aspiration_pump
            )

            # Obtaining bubble sensor
            # Assuming it's connected to the aspiration pump
            self.bubble_sensor = get_bubble_sensor(
                graph,
                self.aspiration_pump
            )
            if self.bubble_sensor is None:
                self.continue_option = self.ContinueCode.NO_BUBBLE_SENSOR
            else:
                self.continue_option = self.ContinueCode.OKAY

            # Ge the heater and the chiller
            heater, chiller = get_heater_chiller(graph, self.from_vessel)

            # Check heater is present
            if self.from_vessel_has_heater is None:
                self.from_vessel_has_heater = True if heater else False

            # Check chiller is present
            if self.from_vessel_has_chiller is None:
                self.from_vessel_has_chiller = True if chiller else False

        if self.rinsing_solvent:
            self.rinsing_solvent_vessel = get_reagent_vessel(
                graph, self.rinsing_solvent)

    def get_rinse_steps(self) -> List[Step]:
        if self.rinsing_solvent is not None:

            # Get the pump speeds
            dispense_speed = self.get_dispense_speed()
            aspiration_speed = self.get_aspiration_speed()

            #  as rinsing is often used to remove residual solid or solution,
            #  assume the volume of rinsing solvent will be greater than the
            #  solvent added for rinsing. Assume a lower cut-off of 2 mL for
            #  final volume of rinsing solvent + residual solid / solution in
            #  vessel
            withdrawal_volume = max(self.rinsing_volume + (
                self.rinsing_volume * self.rinse_withdrawal_excess), 2)

            return [
                Repeat(
                    repeats=self.rinsing_repeats,
                    children=[
                        CMove(
                            from_vessel=self.rinsing_solvent_vessel,
                            to_vessel=self.from_vessel,
                            to_port=self.from_port,
                            volume=self.rinsing_volume,
                        ),
                        CMove(
                            from_vessel=self.from_vessel,
                            from_port=self.from_port,
                            to_vessel=self.to_vessel,
                            to_port=self.to_port,
                            volume=withdrawal_volume,
                            through=self.through_cartridge,
                            aspiration_speed=aspiration_speed,
                            move_speed=self.move_speed,
                            dispense_speed=dispense_speed
                        )
                    ]
                )
            ]
        return []

    def get_move_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        # Get the pump speeds
        dispense_speed = self.get_dispense_speed()
        aspiration_speed = self.get_aspiration_speed()

        return [
            CMove(
                from_vessel=self.from_vessel,
                from_port=self.from_port,
                to_vessel=self.to_vessel,
                to_port=self.to_port,
                volume=self.volume,
                through=self.through_cartridge,
                aspiration_speed=aspiration_speed,
                move_speed=self.move_speed,
                dispense_speed=dispense_speed
            )
        ]

    def get_flush_tubing_steps(self) -> Optional[List[Step]]:
        """Get the list of steps/base steps to execute.

        Returns:
            Optional[List[Step]]: Steps to execute. None if flushing not
                                    required.
        """

        # Return flush step if required, else []
        return [
            FlushTubing(
                to_vessel=self.to_vessel,
                to_port=self.to_port,
                through_cartridge=self.through_cartridge,
                dispense_speed=self.get_dispense_speed(),
            )
        ] if self.flush_tubing else []

    def get_stop_stir_steps(self) -> Optional[List[Step]]:
        """Get StopStir steps if required

        Returns:
            Optional[List[Step]]: StopStir steps, else []
        """

        # Set by executor in _add_all_volumes
        if self.transfer_all:
            # Stirrer present, stop it
            if self.from_vessel_has_stirrer:
                return [StopStir(self.from_vessel)]

        # Not transferring all, not required
        return []

    def get_stop_heatchill_steps(self) -> Optional[List[Step]]:
        """Get the StopHeatChill steps if heater or chiller present

        Returns:
            Optional[List[Step]]: StopHeatChill step if required, else []
        """

        # have either a heater or chiller, stop them
        if self.from_vessel_has_heater or self.from_vessel_has_chiller:
            return [StopHeatChill(vessel=self.from_vessel)]

        # No heater or chiller attached
        return []

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.from_vessel and node_in_graph(
                    graph, self.from_vessel),
                error_msg='from_vessel must be node in graph.',
            ),
            SanityCheck(
                condition=self.to_vessel and node_in_graph(
                    graph, self.to_vessel),
                error_msg='to_vessel must be node in graph.'
            ),
            SanityCheck(
                condition=not self.through or self.through_cartridge,
                error_msg=f'Trying to transfer through "{self.through}" but \
cannot find cartridge containing {self.through}.'
            )
        ]

    def get_dispense_speed(self) -> float:
        """Calculates the dispensing speed of the pumps
        Dispense Speed (mL / min) = (Volume(ml) / time(min))

        Returns:
            float: Dispensing speed of the pump
        """

        if self.time and type(self.volume) != str:
            return self.volume / (self.time / 60)

        return self.dispense_speed

    def get_aspiration_speed(self) -> float:
        """Get the aspiration speed of the pump.
        Speed dependent on whether the solution is viscous or not

        Returns:
            float: Aspiration speed of the pump
        """

        return (
            self.aspiration_speed if not self.viscous
            else DEFAULT_VISCOUS_ASPIRATION_SPEED
        )
