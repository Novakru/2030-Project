"""
.. module:: steps_utility.separate_phases
    :platforms: Unix, Windows
    :synopsis: XDL steps to deal with intricacies of separating phases in
                a separator

"""

from statistics import pstdev, mean
from typing import Callable, Sequence, List, Optional
from networkx import MultiDiGraph

# XDL
from xdl.errors import XDLError
from xdl.utils.misc import SanityCheck
from xdl.utils.graph import undirected_neighbors
from xdl.steps.base_steps import AbstractDynamicStep, Step
from xdl.steps.utils import FTNDuration
from xdl.utils.prop_limits import VOLUME_PROP_LIMIT
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from .liquid_handling import FlushTubing, Transfer
from ..base_step import ChemputerStep
from ..steps_base import ReadConductivitySensor
from ...utils.prop_limits import PORT_PROP_LIMIT
from ...utils.execution import get_cartridge
from ...constants import BOTTOM_PORT, VALID_PORTS, PORT_PROP_TYPE

SEPARATION_DEAD_VOLUME = 1.5
SEPARATION_DEFAULT_PRIMING_VOLUME = 2.5
SEPARATION_DEFAULT_INITIAL_PUMP_SPEED = 40
SEPARATION_DEFAULT_MID_PUMP_SPEED = 40
SEPARATION_DEFAULT_END_PUMP_SPEED = 40

SEPARATION_DEFAULT_INITIAL_PUMP_SPEED_CART = 40
SEPARATION_DEFAULT_MID_PUMP_SPEED_CART = 10
SEPARATION_DEFAULT_END_PUMP_SPEED_CART = 40

class SeparatePhases(ChemputerStep, AbstractDynamicStep):

    PROP_TYPES = {
        'separation_vessel': VESSEL_PROP_TYPE,
        'lower_phase_vessel': VESSEL_PROP_TYPE,
        'upper_phase_vessel': VESSEL_PROP_TYPE,
        'dead_volume_vessel': VESSEL_PROP_TYPE,
        'step_volume': float,
        'lower_phase_port': PORT_PROP_TYPE,
        'upper_phase_port': PORT_PROP_TYPE,
        'dead_volume_port': PORT_PROP_TYPE,
        'lower_phase_through': str,
        'upper_phase_through': str,
        'dead_volume_through': str,
        'failure_vessel': str,
        'max_retries': int,
        'lower_phase_through_cartridge': str,
        'can_retry': bool,
        'separation_vessel_max_volume': float,
        'separation_vessel_pump': str,
        'pump_max_volume': float,
        'conductivity_sensor': str,
        'high_conductivity_phase': str,
    }

    PROP_LIMITS = {
        'step_volume': VOLUME_PROP_LIMIT,
        'lower_phase_port': PORT_PROP_LIMIT,
        'upper_phase_port': PORT_PROP_LIMIT,
        'dead_volume_port': PORT_PROP_LIMIT,
    }

    DEFAULT_PROPS = {
        'dead_volume_vessel': None,
        'step_volume': 1,
        'lower_phase_port': None,
        'upper_phase_port': None,
        'dead_volume_port': None,
        'lower_phase_through': None,
        'upper_phase_through': None,
        'dead_volume_through': None,
        'failure_vessel': None,
        'max_retries': 2,
        'high_conductivity_phase': 'bottom',
    }

    INTERNAL_PROPS = [
        'can_retry',
        'separation_vessel_max_volume',
        'separation_vessel_pump',
        'conductivity_sensor',
        'pump_max_volume',
    ]

    FINISH = 0  # Finish successfully
    READ_CONDUCTIVITY = 1  # Take conductivity measurement
    WITHDRAW = 2  # Withdraw more liquid
    RETRY = 3  # Try separation again if phase change undetected
    TERMINATE = 4  # If phase change undetected 3 times graceful exit.
    RAISE_ERROR = 5  # Raise the error once done

    def __init__(
        self,
        separation_vessel: str,
        lower_phase_vessel: str,
        upper_phase_vessel: str,
        dead_volume_vessel: str = 'default',
        step_volume: float = 'default',
        lower_phase_port: str = 'default',
        upper_phase_port: str = 'default',
        dead_volume_port: str = 'default',
        lower_phase_through: str = 'default',
        upper_phase_through: str = 'default',
        dead_volume_through: str = 'default',
        failure_vessel: str = 'default',
        max_retries: int = 'default',
        lower_phase_through_cartridge: str = None,
        high_conductivity_phase: str = 'default',

        # Internal properties
        can_retry: bool = True,
        separation_vessel_max_volume: float = None,
        separation_vessel_pump: str = None,
        pump_max_volume: float = None,
        conductivity_sensor: str = None,
        **kwargs,
    ) -> None:
        """
        Routine for separating layers in the automated sep funnel based on the
        conductivity sensor. Draws a known amount into the tube, measures
        response, then keeps removing portions and recording the conductivity
        reading until calling `discriminant` with all recorded conductivity
        values results in a return a `True`thy value. When not specified,
        `discriminant` is set to `default_discriminant` sensitive to both
        positive and negative changes in conductivity.

        Args:
            separation_vessel (str): name of the graph node corresponding to
                                   separator flask
            lower_phase_vessel (str): name of the flask the lower phase will be
                                      deposited to
            upper_phase_vessel (str): name of the flask the upper phase will be
                                      deposited to
            dead_volume_vessel (str or None): name of the flask the dead volume
                will be deposited to; if not set dead volume is not removed
            step_volume (float): volume of the individual withdrawals in mL
            discriminant (function): callback which gets passed all conductivity
                values up to current point and returns True or False indicating
                whether or not a phase change has been detected
            lower_phase_port (str): Optional. Port on lower_phase_target to use.
            upper_phase_port (str): Optional. Port on upper_phase_target to use.
            dead_volume_port (str): Optional. Port on dead_volume_target to use.
            lower_phase_through (str): Optional. Node to go through on way to
                lower_phase_target.
            upper_phase_through (str): Optional. Node to go through on way to
                upper_phase_target.
            dead_volume_through (str): Optional. Node to go through on way to
                dead_volume_target.
            lower_phase_through_cartridge (str): Internal property used to flush
                tubing in the case that it can't be done as part of a Transfer
                step.
            high_conductivty_phase (str): Optional. Possible values are either
                'top' or 'bottom'. Defines the expected sign of conductivity
                change at the phase boundary.
        """
        super().__init__(locals())
        self.continue_options = {
            self.FINISH: lambda: [],
            self.READ_CONDUCTIVITY: self.continue_read_conductivity,
            self.WITHDRAW: self.continue_withdraw,
            self.RETRY: self.continue_retry,
            self.TERMINATE: self.continue_terminate,
            self.RAISE_ERROR: self.continue_raise_error
        }
        negative_edge = self.high_conductivity_phase == 'bottom'
        positive_edge = not negative_edge
        self.discriminant = self.default_discriminant(positive_edge,
                                                      negative_edge)
        self.reset()

    def reset(self, retries: bool = True):
        """Reset all instance variables dealing with separation

        Args:
            retries (bool, optional): Reset the retries flag. Defaults to True.
        """

        self.pump_current_volume = 0  # Current volume in separation vessel pump
        self.readings = []

        if retries:
            self.retries = 0

        self.total_withdrawn = 0
        self.continue_option = self.READ_CONDUCTIVITY
        self.done = False

    def default_discriminant(
        self,
        positive_edge=False,
        negative_edge=False,
        sensitivity=10,
        min_points=7
    ) -> Callable[[Sequence[float]], bool]:
        """
        Factory method to return a customized discriminant function with the
        given properties.

        Args:
            positive_edge (bool, optional): Detect phase change when
                conductivity measurement goes up.
            negative_edge (bool, optional): Detect phase change when
                conductivity measurment goes down.
            sensitivity (int, optional): How many standard deviations away from
                the window mean should a conductivity reading be to be
                interpreted as a phase change.
            min_points (int, optional): Minimum number of conductivity
                measurement before a phase change can occur. The same paramter
                dictates the window size for the moving average:
                `window_size = min_points - 2`.

        Returns:
            Callable: A (disciminant) function that takes a series of
                measurements and decides whether a phase change has occurred.
        """

        def discriminant(points: Sequence[float]) -> bool:
            """
            Discriminant function which analyses a series of readings from the
            conductivity sensor for a step-change that is characteristic of a
            phase change in liquid-liquid extraction.

            Args:
                points (Sequence): All conductivity measurements performed so
                    far, with `points[0]` being the first measurement and
                    `points[-1]` the current one.

            Returns:
                bool: Whether phase change has occurred (True) or not (False).
            """

            # Collect at least the number of data points specified in
            # 'min_points' before making a judgement.
            if len(points) < min_points:
                return False

            # 1) Calculate the standard deviation of the previous conductivity
            #    readings (the 7th last to the 3rd last reading are included).
            #    A lower limit of 5 is set to the standard deviation (the
            #    current design of the conductivity sensor produces very stable
            #    readings with the standard deviation being often close to
            #    zero).
            std_previous = max(pstdev(points[-(min_points + 1): -3]), 5.0)

            # 2) Calculate the average signal value of the previous conduvitity
            #    readings (the 7th last to the 3rd last reading are included).
            average_pervious = mean(points[-(min_points + 1):-3])

            # 3) Calculate the difference betwee the previous average
            #    conductivity readings and the last and second last reading.
            delta_previous = points[-2] - average_pervious
            delta_new = points[-1] - average_pervious

            # 4) Check whether the last two readings both fulfill the
            #    characteristics of a phase change (steps 4a to 4c).
            #
            # 4a) For an genuine phase change, the last two readings
            #     deviate from the previous average in the same direction.
            #     (for example [650, 649, 649, 650, 651, 400, 900] is not
            #     a valid signature of a phase change).
            sign = (lambda x: x and (1, -1)[x < 0])
            if sign(delta_new) != sign(delta_previous):
                return False

            # 4b) The last reading must deviate from the previous average by
            #     at least 90 % of the difference between the second last
            #     reading and the previous average. This measure is intended
            #     to prevent narrow spikes in the condductivity to trigger
            #     false-positive phase detection (for example [650, 649, 649,
            #     650, 651, 400, 600]) would be considered such a spike and
            #     not a phase change).
            if abs(delta_new) < abs(delta_previous) * 0.9:
                return False

            # 4c) If the deviation of both the last and second last
            #     reading from the previous average is larger than the
            #     standard deviation multiplied by the sensitivity factor
            #     a phase change has likely occured. If non-default values
            #     for the positive_edge and negative_edge have been
            #     provided, it is also required that change in conducitivity
            #     follows the expected direction (if positive_edge is
            #     true the change in conductivity must be positive - for
            #     example: [650, 649, 649, 650, 651, 1021, 1049]).
            if (((delta_previous > sensitivity * std_previous
                and positive_edge)
                or (-delta_previous > sensitivity * std_previous
                    and negative_edge))
                and ((delta_new > sensitivity * std_previous
                     and positive_edge)
                or (-delta_new > sensitivity * std_previous
                    and negative_edge))):
                return True
            else:
                # No phase change occured.
                return False

        return discriminant

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check

        Raises:
            XDLError: Certain pieces of hardware were not found attached to
                        certain vessels
        """

        self.graph = graph

        # Determine if retries are possible
        self.check_if_can_retry(graph)

        # Set vars to None
        self.pump_max_volume = None
        self.separation_vessel_pump = None
        self.separation_vessel_max_volume = None

        # Iterate through each neighboring node of the separation vessel
        for neighbor in undirected_neighbors(graph, self.separation_vessel):
            # Current neighbor is a ChemputerValve
            if graph.nodes[neighbor]['class'] == 'ChemputerValve':
                # Iterate through the valve's neighbors
                for valve_neighbor in graph.neighbors(neighbor):
                    # Valve neighbor is a ChemputerPump
                    if graph.nodes[valve_neighbor]['class'] == 'ChemputerPump':
                        # Set the separation pump and volume
                        self.separation_vessel_pump = valve_neighbor
                        self.pump_max_volume = graph.nodes[
                            valve_neighbor]['max_volume']
                        break

            # Current neighbor is a Conductivity sensor
            elif graph.nodes[neighbor]['class'] == 'ConductivitySensor':
                # Set the sensor
                self.conductivity_sensor = neighbor

        # Set the separation volume
        self.separation_vessel_max_volume = graph.nodes[
            self.separation_vessel]['max_volume']

        # No separation pump found, raise error
        if not self.separation_vessel_pump:
            raise XDLError(
                f"No pump attached to {self.separation_vessel}"
            )

        # No conductivity sensor found, raise error
        if not self.conductivity_sensor:
            raise XDLError(
                f"No conductivity sensor attached to {self.separation_vessel}"
            )

        # Obtain the through cartridge if not defined
        if not self.lower_phase_through_cartridge and self.lower_phase_through:
            self.lower_phase_through_cartridge = get_cartridge(
                graph, self.lower_phase_through)

    def get_pump_speeds(self, through: bool):
        """Set pump speeds dependent on going through a cartridge or node

        Args:
            through (bool): Use through speeds
        """

        # Going through a cartridge, use through speeds
        if through:
            self.init_pump_speed = SEPARATION_DEFAULT_INITIAL_PUMP_SPEED_CART
            self.mid_pump_speed = SEPARATION_DEFAULT_MID_PUMP_SPEED_CART
            self.end_pump_speed = SEPARATION_DEFAULT_END_PUMP_SPEED_CART

        # Use default speeds
        else:
            self.init_pump_speed = SEPARATION_DEFAULT_INITIAL_PUMP_SPEED
            self.mid_pump_speed = SEPARATION_DEFAULT_MID_PUMP_SPEED
            self.end_pump_speed = SEPARATION_DEFAULT_END_PUMP_SPEED

    def check_if_can_retry(self, graph: MultiDiGraph):
        """Determines if the separation can be repeated

        Args:
            graph (MultiDiGraph): [description]
        """

        # Lower phase vessel is defined
        if self.lower_phase_vessel:
            # Lower phase vessel is a waste vessel, cannot retry
            if (
                graph.nodes[self.lower_phase_vessel]['class']
                == 'ChemputerWaste'
            ):
                self.can_retry = False

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.lower_phase_vessel,
            ),
            SanityCheck(
                condition=self.upper_phase_vessel,
            ),
            SanityCheck(
                condition=self.separation_vessel,
            ),
            SanityCheck(
                condition=self.separation_vessel_pump,
            ),
            SanityCheck(
                condition=self.lower_phase_vessel != self.upper_phase_vessel,
                error_msg=f'Trying to separate phases both into the same vessel\
 ({self.lower_phase_vessel}).'
            )
        ]

    def final_sanity_check(self, graph: MultiDiGraph):
        """Do the final sanity checks for the step

        Args:
            graph (MultiDiGraph): Graph to check
        """

        super().final_sanity_check(graph)
        self.sanity_check_transfer_ports(graph)

    def sanity_check_transfer_ports(self, graph: MultiDiGraph):
        """Checks that no incorrect ports are being used

        Args:
            graph (MultiDiGraph): Graph to check
        """

        # Iterate through methods
        for fn in [
            self.lower_phase_stepwise_withdraw_step,
            self.lower_phase_separation_pump_dispense_step,
            self.prime_sensor_step,
            self.upper_phase_withdraw_step,
            self.dead_volume_withdraw_step,
            self.continue_retry,
        ]:
            # Obtain steps from each method
            steps = fn()

            # Convert to list if not already
            if type(steps) != list:
                steps = [steps]

            # Iterate through steps looking for Transfer step
            for step in steps:
                if type(step) == Transfer:
                    # Check the ports
                    self.test_valid_transfer_ports(graph, step)

    def test_valid_transfer_ports(self, graph: MultiDiGraph, step: Step):
        """Test that the ports being used in Transfer steps are valid ports

        Args:
            graph (MultiDiGraph): Grpah to check
            step (Step): Step to check

        Raises:
            XDLError: Invalid ports are being used
        """

        # Get the from_port from the graph if not present
        if step.from_port is not None:
            from_class = graph.nodes[step.from_vessel]['class']

            # Check the ports
            try:
                assert str(step.from_port) in VALID_PORTS[from_class]

            # Ports are invalid
            except AssertionError:
                raise XDLError(
                    f'"{step.from_port}" is not a valid port for {from_class}'
                )

        # Get the to_port form the graph if not present
        if step.to_port is not None:
            to_class = graph.nodes[step.to_vessel]['class']

            # Check the ports
            try:
                assert str(step.to_port) in VALID_PORTS[to_class]

            # Ports are invalid
            except AssertionError:
                raise XDLError(
                    f'"{step.to_port}" is not a valid port for {to_class}'
                )

    def on_start(self) -> List[Step]:
        """Initial conductivity sensor reading.

        Returns:
            List[Step]: Conductivity reading steps
        """

        self.continue_option = self.WITHDRAW
        return [
            self.prime_sensor_step(),
            ReadConductivitySensor(
                sensor=self.conductivity_sensor,
                on_reading=self.on_conductivity_sensor_reading
            ),
        ]

    def on_continue(self) -> Optional[List[Step]]:
        """Either finish, take conductivity reading, or withdraw more liquid.

        Returns:
            Optional[List[Step]]: Read conductivity or withdraw liquid if not
                                not finished, else []
        """

        return (
            self.continue_options[self.continue_option]() if not self.done
            else []
        )

    def continue_read_conductivity(self) -> List[Step]:
        """Continue to read conductivity.

        Returns:
            List[Step]: ReadCOnductivity step
        """

        # Set the continue option
        self.continue_option = self.WITHDRAW

        return [
            ReadConductivitySensor(
                sensor=self.conductivity_sensor,
                on_reading=self.on_conductivity_sensor_reading
            )
        ]

    def continue_withdraw(self) -> List[Step]:
        """Continue withdrawing.

        Returns:
            List[Step]: Withdraw steps
        """

        # Set continue option
        self.continue_option = self.READ_CONDUCTIVITY

        # Get withdraw steps
        steps = self.lower_phase_stepwise_withdraw_step()

        # If phase separation unsuccessful
        if self.total_withdrawn >= self.separation_vessel_max_volume:
            # Either retry or raise XDLError.
            if self.retries < self.max_retries and self.can_retry:
                self.logger.info('Separation failed. Retrying...')
                self.continue_option = self.RETRY
            else:
                self.continue_option = self.TERMINATE

        return steps

    def continue_retry(self) -> List[Step]:
        """Continue with retrying separation.

        Returns:
            List[Step]: Separation steps
        """

        steps = []

        # Increment retry counter
        self.retries += 1

        # Max volume is defined, add separations steps
        if self.pump_max_volume:
            steps.append(self.lower_phase_separation_pump_dispense_step())

        #  Add Transfer step
        steps.append(self.get_retry_transfer_step())

        # Reset all instance variables
        self.reset(retries=False)

        # Add in Start steps
        steps.extend(self.on_start())

        return steps

    def get_retry_transfer_step(self):
        """Get step to transfer mixture back to separation flask for another
        attempt at separation.
        """
        # Don't include lower phase port so that withdrawal from filter still
        # works. Default port choice should suffice.
        return Transfer(
            from_vessel=self.lower_phase_vessel,
            to_vessel=self.separation_vessel,
            to_port=BOTTOM_PORT,
            volume=self.total_withdrawn,
            flush_tubing=True,
        )

    def continue_terminate(self) -> List[Step]:
        """Contiue with termination steps

        Returns:
            List[Step]: Termination steps
        """

        # Set continue option
        self.continue_option = self.RAISE_ERROR

        # Failure vessel given, move mixture there
        if self.failure_vessel is not None:
            return (
                [self.get_transfer_pump_to_failure_vessel_step()]
                + self.get_transfer_lower_phase_to_failure_vessel_step()
            )

        # No failure vessel given, just raise error
        return []

    def continue_raise_error(self):
        """Error to raise when separation failed

        Raises:
            XDLError: Separation failed after N attempts
        """

        raise XDLError(
            f'Attempted and failed separation {self.retries + 1} times.\
Lower phase sent to \"{self.failure_vessel}\".\n\
Please check the appropriate log files for conductivity sensor readings.\
\n{self.properties}')

    def on_finish(self) -> List[Step]:
        """Phase change detected. Send phases where they are supposed to go.

        Returns:
            List[Step]: Transfer steps for the phases
        """

        steps = []

        # Send remaining lower phase in pump to lower_phase_vessel.
        if self.pump_current_volume:
            steps.append(self.lower_phase_separation_pump_dispense_step(
                flush_tubing=True))

        # If there is no Transfer, do flush tubing as explicit step.
        else:
            steps.append(
                self.get_final_flush_tubing_step()
            )

        # Withdraw dead volume if dead_volume_target given.
        steps.extend(self.dead_volume_withdraw_step())

        # Send upper phase to upper_phase_vessel.
        steps.extend(self.upper_phase_withdraw_step())

        return steps

    def get_final_flush_tubing_step(self) -> Step:
        """Final flush tubing step, needed if final step does not involve a
        Transfer.
        """
        return FlushTubing(
            to_vessel=self.lower_phase_vessel,
            to_port=self.lower_phase_port,
            through_cartridge=self.lower_phase_through_cartridge,
        )

    def prime_sensor_step(self) -> Step:
        """Prime the sensor by moving liquid from the separator to the lower
        phase vessel

        Returns:
            Step: Transfer step for movement
        """

        # Set teh pump speeds
        self.get_pump_speeds(self.lower_phase_through)

        return Transfer(
            from_vessel=self.separation_vessel,
            to_vessel=self.lower_phase_vessel,
            volume=SEPARATION_DEFAULT_PRIMING_VOLUME,
            aspiration_speed=self.init_pump_speed,
            move_speed=self.mid_pump_speed,
            dispense_speed=self.end_pump_speed,
            to_port=self.lower_phase_port,
            through=self.lower_phase_through
        )

    def lower_phase_stepwise_withdraw_step(self) -> List[Step]:
        """Withdrawl of the lower phase of the separation

        Returns:
            List[Step]: Transfer steps
        """

        # Set the pump speeds
        self.get_pump_speeds(self.lower_phase_through)

        steps = [
            Transfer(
                from_vessel=self.separation_vessel,
                to_vessel=self.separation_vessel_pump,
                volume=self.step_volume,
                aspiration_speed=self.init_pump_speed,
                move_speed=self.mid_pump_speed,
                dispense_speed=self.end_pump_speed,
            )
        ]

        # Volume exceeds max volume for the pump
        if self.pump_current_volume + self.step_volume > self.pump_max_volume:
            # Add stepwise addition at start
            steps.insert(0, self.lower_phase_separation_pump_dispense_step())

            # Reset the pump volume
            self.pump_current_volume = 0

        # Increment volumes from step_volumes
        self.pump_current_volume += self.step_volume
        self.total_withdrawn += self.step_volume

        return steps

    def lower_phase_separation_pump_dispense_step(
            self, flush_tubing=False) -> Step:
        """Movement of the lower phase of the separation

        Args:
            flush_tubing (bool): If True, tubing will be flushed with inert
                gas after transfer.

        Returns:
            Step: Transfer step
        """

        # Set pump speeds
        self.get_pump_speeds(self.lower_phase_through)

        return Transfer(
            from_vessel=self.separation_vessel_pump,
            to_vessel=self.lower_phase_vessel,
            to_port=self.lower_phase_port,
            volume=self.pump_current_volume,
            aspiration_speed=self.init_pump_speed,
            move_speed=self.mid_pump_speed,
            dispense_speed=self.end_pump_speed,
            through=self.lower_phase_through,
            flush_tubing=flush_tubing,
        )

    def upper_phase_withdraw_step(self) -> Optional[List[Step]]:
        """Withdrawl of the upper phase of the separation

        Returns:
            Optional[List[Step]]: Transfer steps, None if separation vessel
                                is the upper phase
        """

        # Set pump speeds
        self.get_pump_speeds(self.upper_phase_through)

        # Separation vessel is the upper phase, not needed
        if self.separation_vessel == self.upper_phase_vessel:
            return []

        return [Transfer(
            from_vessel=self.separation_vessel,
            to_vessel=self.upper_phase_vessel,
            volume='all',
            aspiration_speed=self.init_pump_speed,
            move_speed=self.mid_pump_speed,
            dispense_speed=self.end_pump_speed,
            to_port=self.upper_phase_port,
            through=self.upper_phase_through,
            flush_tubing=True,
        )]

    def dead_volume_withdraw_step(self) -> Optional[List[Step]]:
        """Withdrawl of the dead volume

        Returns:
            Optional[List[Step]]: Transfer step, None if dead volume not used
        """

        # Using a dead volume vessel
        if self.dead_volume_vessel:
            # Set pump speeds
            self.get_pump_speeds(self.dead_volume_through)

            # Return Transfer
            return [Transfer(
                from_vessel=self.separation_vessel,
                to_vessel=self.dead_volume_vessel,
                volume=SEPARATION_DEAD_VOLUME,
                aspiration_speed=self.init_pump_speed,
                move_speed=self.mid_pump_speed,
                dispense_speed=self.end_pump_speed,
                to_port=self.dead_volume_port,
                through=self.dead_volume_through,
                flush_tubing=True,
            )]

        # No dead volume needed, return []
        return []

    def get_transfer_lower_phase_to_failure_vessel_step(self) -> Step:
        """Get step to transfer lower phase to failure vessel."""
        # Check lower_phase_vessel is not the same as failure_vessel, and it is
        # not a waste vessel (can_retry signifies that lower_phase_vessel is a
        # waste vessel).
        if self.lower_phase_vessel != self.failure_vessel and self.can_retry:
            return [Transfer(
                from_vessel=self.lower_phase_vessel,
                to_vessel=self.failure_vessel,
                volume=self.total_withdrawn - self.pump_current_volume,
                flush_tubing=True,
            )]
        return []

    def get_transfer_pump_to_failure_vessel_step(self) -> Step:
        """Get step to transfer whatever is still in pump to failure vessel."""
        return Transfer(
            from_vessel=self.separation_vessel_pump,
            to_vessel=self.failure_vessel,
            volume=self.pump_current_volume,
            aspiration_speed=SEPARATION_DEFAULT_INITIAL_PUMP_SPEED,
            move_speed=SEPARATION_DEFAULT_MID_PUMP_SPEED,
            dispense_speed=SEPARATION_DEFAULT_END_PUMP_SPEED,
        )

    def on_conductivity_sensor_reading(self, reading: float):
        """Set the reading once received from the conductivity sensor

        Args:
            reading (float): COnductivity sensor reading
        """

        # Successful separation, separation complete
        if reading == -1:
            self.logger.info('Phase separation complete.')
            self.done = True

        # Readings have been already been defined
        elif self.readings:
            # Add new reading to list of existing readings
            self.readings.append(reading)
            self.logger.info("Sensor reading is {0}.".format(self.readings[-1]))

            # Still in the same phase
            if not self.discriminant(self.readings):
                self.logger.info("Nope still the same phase.")

            # Phase change has been detected, finished
            else:
                self.logger.info("Phase changed! Hurrah!")
                self.done = True

        # Set current readings to new reading
        else:
            self.readings = [reading]

    def get_simulation_steps(self) -> List[Step]:
        """Return all possible steps that can be executed.

        Returns:
            List[Step]: All possible steps that can be executed for use in
                simulation.
        """

        # Define all steps that can be executed during phase separation
        simulation_steps = (
            self.dead_volume_withdraw_step()
            + self.upper_phase_withdraw_step()
            + [self.lower_phase_separation_pump_dispense_step()]
            + self.lower_phase_stepwise_withdraw_step()
            + [self.prime_sensor_step()]
            + [self.get_final_flush_tubing_step()]
        )

        # Only add these steps if failure vessel is not None
        if self.failure_vessel is not None:
            simulation_steps.extend((
                [self.get_transfer_pump_to_failure_vessel_step()]
                + self.get_transfer_lower_phase_to_failure_vessel_step()
            ))

        # Only add this step if retrying is possible, i.e. lower phase vessel is
        # not waste.
        if self.can_retry:
            simulation_steps.append(self.get_retry_transfer_step())

        # Make sure no steps have 0 volume as this stops them failing in
        # Chempiler simulation.
        for step in simulation_steps:
            if 'volume' in step.properties and step.volume == 0:
                step.volume = 1

        return simulation_steps

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculate duration of step

        Args:
            graph (MultiDiGraph): Graph to search

        Returns:
            FTNDuration: Duration of step
        """
        # Educated guess. Not based on measured data.
        min_value, most_likely_value, max_value = 5 * 60, 10 * 60, 20 * 60

        # Takes much longer if transferring through something
        if self.lower_phase_through or self.upper_phase_through:
            min_value += 30 * 60
            most_likely_value += 2 * 60 * 60
            max_value += 6 * 60 * 60

        return FTNDuration(min_value, most_likely_value, max_value)
