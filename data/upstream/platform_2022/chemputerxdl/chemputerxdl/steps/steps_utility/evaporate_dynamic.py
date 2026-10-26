"""
Dynamic XDL step for dynamic evaporation.
The process is stopped when the rotavap finds the evaporation endpoint
or when the hard time limit has been reached.
"""
import time
import datetime

from typing import List
from networkx import MultiDiGraph

from xdl.steps.base_steps import AbstractDynamicStep
from xdl.utils.misc import SanityCheck
from xdl.constants import VESSEL_PROP_TYPE
from xdl.steps.base_steps import Step

from ..steps_base import CR300RotavapGetStatus, CR300RotavapGetChillerStatus
from ..steps_utility import Wait

class EvaporateDynamic(AbstractDynamicStep):
    """Evaporate in 'auto' mode until the evaporator detects the evaporation
    end-point or the hard time limit has been reached.

    Args:
        vessel (str): Name of the rotary evaporator.
        max_time (float): Maximum time the process can take.

    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'max_time': float,
    }

    WAIT_TIME = 20  # Wait time between enquiring the rotavap status in seconds.
    CHILLER_TEMP_OFFSET = 2
    # If the chiller temperature is less than 2 °C above the set-point,
    # the evaporation process starts.

    def __init__(
            self,
            # Mandatory properties
            vessel: str,
            max_time: float,
            **kwargs
    ):
        super().__init__(locals())

        self.ready_to_start_evaporation = False
        # TODO: Check whether the R300 rotavap has a chiller attached.
        self.start_time: float = None
        self.finished = False

    def on_prepare_for_execution(self, graph):
        """Add any extra properties needed before execution using graph."""
        pass

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """
        return []

    def on_start(self):
        self.logger.debug("Starting dynamic evaporation step"
                          f"on device '{self.vessel}'.")

        return []

    def on_continue(self):
        if self.finished:
            self.logger.debug('Dynamic evaporation is complete.')
            return []
        elif self.ready_to_start_evaporation:
            return self.continue_wait_and_read_status()
        else:
            return self.continue_wait_for_chiller()

    def continue_wait_for_chiller(self):
        """Waiting for the chiller cooling the condenser
        to reach the target temperature."""
        self.logger.debug("Reading current chiller temperature "
                          "and compare it to set-point.")
        return [
            Wait(EvaporateDynamic.WAIT_TIME),
            CR300RotavapGetChillerStatus(
                rotavap_name=self.vessel,
                on_reading=self.on_reading_chiller_temp)
        ]

    def on_reading_chiller_temp(self, current_temp, target_temp):
        """
        Callback function for checking on chiller to reach
        the target temperature. Next action is either to contune
        waiting or the start evaporation process.
        """
        if current_temp - target_temp < EvaporateDynamic.CHILLER_TEMP_OFFSET:
            self.logger.debug("Chiller reached target temperature "
                              "and is ready for the evaporation process.")
            self.ready_to_start_evaporation = True
            self.start_time = time.time()
        else:
            self.logger.debug("Chiller has not reached target temperature yet. "
                              f"Current temp: {current_temp} °C. "
                              f"Target temp: {target_temp} °C")

    def continue_wait_and_read_status(self):
        """Read evaporator status during continue loop."""
        self.logger.debug('Reading status of evaporator.')
        return [
            Wait(EvaporateDynamic.WAIT_TIME),
            CR300RotavapGetStatus(
                rotavap_name=self.vessel,
                on_reading=self.on_reading_status)
        ]

    def on_reading_status(self, is_idle):
        """
        Callback function for status reading in continue loop.
        Next action is either to continue evaporation (waiting)
        or finishing the step.
        """
        time_left = self.max_time - (time.time() - self.start_time)
        if time_left <= 0:
            self.logger.warning(f"Evaporation step on device '{self.vessel}' "
                                "exceeded its time limit and is terminated. "
                                "The evaporation process may not be "
                                "complete.")
            self.finished = True
        elif is_idle:
            total_time = datetime.timedelta(
                seconds=(round(time.time() - self.start_time)))
            self.logger.debug("Evaporation process is complete in "
                              f"{total_time}.")
            self.finished = True
        else:
            ftime_left = datetime.timedelta(seconds=(round(time_left)))
            self.logger.debug("Evaporation process is on-going. Time left: "
                              f"{ftime_left} min.")

    def get_simulation_steps(self) -> List[Step]:
        """In simulation do not inquire device status.
        Wait for the maximal time instead."""
        self.start_time = time.time()
        return [
            Wait(self.max_time),
            CR300RotavapGetStatus(
                rotavap_name=self.vessel,
                on_reading=self.on_reading_status)
        ]

    def on_finish(self):
        """Finishing up - there's nothing to do here."""
        return []
