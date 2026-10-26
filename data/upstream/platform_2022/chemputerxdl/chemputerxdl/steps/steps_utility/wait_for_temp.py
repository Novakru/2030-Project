"""
.. module:: steps_utility.wait_for_temp
    :platforms: Unix, Windows
    :synopsis: XDL step wait for heater/chiller to reach target temperature

"""

from typing import List, Optional
import time
from networkx import MultiDiGraph

# XDL
from xdl.utils.misc import SanityCheck
from xdl.steps.base_steps import AbstractDynamicStep
from xdl.steps.base_steps import Step
from xdl.steps.utils import FTNDuration
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from ..base_step import ChemputerStep
from ..steps_utility import Wait
from ..steps_base import (
    CTemperatureControllerGetTempSetpoint,
    CTemperatureControllerGetTemp,
)
from ...utils.execution import get_temperature_controller
from ...utils.misc import pretty_duration

class WaitForTemp(ChemputerStep, AbstractDynamicStep):
    """Wait for heater/chiller connected to vessel to reach target temperature
    that it has been set to previously.

    Args:
        vessel (str): Vessel to wait to reach target temperature.
        heater (str): Internal property. Heater node name to wait to reach
            target temperature.
        chiller (str): Internal property. Chiller node name to wait to reach
            target temperature. Only one of chiller and heater has to be not
            None.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'temperature_controller': str,
        'relaxed_rt_threshold': float,
        'relaxed_rt_threshold_timeout': float,
    }

    DEFAULT_PROPS = {
        'relaxed_rt_threshold': 5,
        'relaxed_rt_threshold_timeout': 600,
    }

    INTERNAL_PROPS = [
        'temperature_controller'
    ]

    WAIT_TIME_BETWEEN_READINGS = 20
    THRESHOLD = 0.5

    def __init__(
        self,
        vessel: str,
        relaxed_rt_threshold: Optional[float] = 'default',
        relaxed_rt_threshold_timeout: Optional[float] = 'default',
        temperature_controller: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Initialise state.

        State:
            setpoint (float): Target temperature step is waiting to reach.
            setpoint_is_rt (bool): True if setpoint is room temperature,
                otherwise False
            approach (str): 'up' if temperature is increasing to target temp,
                'down' if temperature is decreasing to target temp.
            relaxed_rt_threshold_timeout_start (float): Time at which temp
                reached setpoint +- self.relaxed_rt_threshold.
        """
        super().__init__(locals())

        # Step start time as returned by ``time.time()``
        self._start_time = None

        self.target_temp = None  # Temperature trying to be reached.

        # True if setpoint is RT, False otherwise.
        self.target_temp_is_rt = None

        # 'up' or 'down', direction of approach to target temp
        self.approach = None

        # Time at which setpoint +- relaxed RT threshold was reached.
        self.relaxed_rt_threshold_timeout_start = None

        # Flag to indicate on_continue loop should break
        self._finished = False

    #####################
    # Lifecycle Methods #
    #####################

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Get node name of heater or chiller connected to self.vessel."""
        self.graph = graph

        # Get temperature controller node.
        self.temperature_controller = get_temperature_controller(
            graph, self.vessel)

    def sanity_checks(self, graph: MultiDiGraph):
        return [
            SanityCheck(
                condition=self.temperature_controller,
                error_msg=f'Cannot find temperature controller attached to\
 {self.vessel}.'
            )
        ]

    def on_start(self) -> List[Step]:
        """Get setpoint of heater or chiller and store in self.target_temp
        variable.
        """
        self._start_time = time.time()
        return self.get_temp_setpoint_steps()

    def on_continue(self) -> List[Step]:
        """Take temperature reading, with callback to change self._finished as
        appropriate, then wait before next loop.
        """
        # Reached target temp, return empty list and finish.
        if self._finished:
            return []

        # Take new reading and wait longer.
        return (
            self.get_temp_step()
            + self.get_wait_step()
        )

    def on_finish(self) -> List[Step]:
        """Temperature reached, finish.

        Returns:
            List[Step]: Nothing else needs done.
        """
        return []

    ################
    # Step Methods #
    ################

    def get_temp_setpoint_steps(self) -> List[Step]:
        return [
            CTemperatureControllerGetTempSetpoint(
                temperature_controller=self.temperature_controller,
                on_reading=self.on_setpoint_reading
            )
        ]

    def get_temp_step(self) -> List[Step]:
        return [
            CTemperatureControllerGetTemp(
                temperature_controller=self.temperature_controller,
                on_reading=self.on_temp_reading,
            )
        ]

    def get_wait_step(self) -> List[Step]:
        """Get Wait step to execute between temperature readings."""
        return [Wait(time=self.WAIT_TIME_BETWEEN_READINGS)]

    #####################
    # Reading Callbacks #
    #####################

    def on_setpoint_reading(self, reading: float) -> None:
        """Set self.target_temp when heater/chiller setpoint is read."""
        self.target_temp = reading
        self.target_temp_is_rt = 18 <= self.target_temp <= 25

    def on_temp_reading(self, reading: float) -> None:
        """Take temperature reading, and decide whether to finish or not.

        Finish conditions:
            reading == self.target_temp +/- self.THRESHOLD
            self.target_temp_is_rt and relaxed RT threshold timeout exceeded

        Args:
           reading (float): Temperature reading
        """
        # Log temp reading for debugging purposes
        time_elapsed = time.time() - self._start_time
        self.logger.info(
            f'Waiting for {self.vessel} to reach {self.target_temp:.1f} °C.\
 Current temperature is {reading:.1f} °C.\
 Time elapsed: {pretty_duration(time_elapsed)}'
        )

        # Get approach direction on first reading
        if not self.approach:
            self.approach = get_approach_direction(self.target_temp, reading)

            # reading == self.target_temp
            if not self.approach:
                self._finished = True
                return

        # Check for simple completion (temp is within setpoint +- THRESHOLD)
        if self.reached_temp(reading):
            self._finished = True
            return

        # Used relaxed_rt_threshold if target temperature is RT. This was added
        # as sometimes when switching the heater/chiller off and waiting for RT
        # to be reached, the temp would never quite get there and WaitForTemp
        # would go on forever
        if self.target_temp_is_rt:

            # Temp is within relaxed RT threshold, check if timeout
            # exceeded and finish if so.
            if self.relaxed_rt_threshold_timeout_start:
                if self.exceeded_relaxed_rt_threshold_timeout():
                    self._finished = True
                    return

            # Check if temp has reached relaxed RT threshold yet
            elif self.reached_relaxed_rt_threshold(reading):

                # Store the time that the temp reached relaxed RT
                # threshold for calculating whether the timeout has
                # been exceeded later.
                self.relaxed_rt_threshold_timeout_start = time.time()

    #########
    # Utils #
    #########

    def reached_temp(self, reading: float) -> bool:
        """Return True if target temp has been reached, otherwise False.

        Args:
            reading (float): Temperature reading.
        """
        if (self.approach == 'up'
                and reading >= self.target_temp - self.THRESHOLD):
            return True

        elif (self.approach == 'down'
                and reading <= self.target_temp + self.THRESHOLD):
            return True

        return False

    def reached_relaxed_rt_threshold(self, reading: float) -> bool:
        """Return True if relaxed RT threshold temp has been reached, otherwise
        False.

        Args:
            reading (float): Temperature reading.
        """
        if self.approach == 'up':
            if (reading
                    >= self.target_temp - self.relaxed_rt_threshold):
                return True

        elif self.approach == 'down':
            if (reading
                    <= self.target_temp + self.relaxed_rt_threshold):
                return True

        return False

    def exceeded_relaxed_rt_threshold_timeout(self):
        """Return True if relaxed RT threshold timeout has been exceeded,
        otherwise False.
        """
        # Get time elapsed since relaxed RT threshold was reached.
        time_elapsed = time.time() -\
            self.relaxed_rt_threshold_timeout_start

        # If time elapsed since relaxed RT threshold was reached
        # exceeds timeout, finish
        if time_elapsed > self.relaxed_rt_threshold_timeout:
            return True

        return False

    #########
    # Other #
    #########

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculate the duration of this step

        Args:
            graph (MultiDiGraph): Graph to search

        Returns:
            FTNDuration: Duration of the step
        """
        # Arbitrary. Should really be overridden in higher level steps using
        # this step.
        return FTNDuration(60 * 5, 60 * 60, 5 * 60 * 60)

def get_approach_direction(target_temp, initial_temp):
    """Get approach direction 'up' or 'down' based on target temp and initial
    temp.
    """
    if initial_temp < target_temp:
        return 'up'
    elif initial_temp > target_temp:
        return 'down'
    return None
