"""
.. module:: steps_base.chiller
    :platforms: Unix, Windows,
    :synopsis: Base steps for Chemputer Chillers

"""

from typing import List, Tuple
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import AbstractBaseStep
from xdl.utils.prop_limits import (
    TEMP_PROP_LIMIT, TIME_PROP_LIMIT, PERCENT_RANGE_PROP_LIMIT
)
from xdl.utils.misc import SanityCheck
from xdl.constants import VESSEL_PROP_TYPE
from xdl.steps.utils import FTNDuration

# Relative
from ..base_step import ChemputerStep
from ...utils.execution import get_chiller
from ...constants import JULABO_CF41, HUBER_PETITE_FLEUR

class CStartChiller(ChemputerStep, AbstractBaseStep):
    """Starts the recirculation chiller.

    Args:
        vessel (str): Vessel to chill. Name of the node the chiller is attached
        to.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'chiller': str,
    }

    INTERNAL_PROPS = ['chiller']

    def __init__(self, vessel: str, chiller: str = None, **kwargs) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph):
        self.chiller = get_chiller(graph, self.vessel)

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.vessel, self.chiller], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object.
            logger (Logger, optional): Logger. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Executed successfully.
        """
        chempiler.acquire(self.chiller).start()
        chempiler.release(self.chiller)
        return True

class CStopChiller(ChemputerStep, AbstractBaseStep):
    """Stops the recirculation chiller.

    Args:
        vessel (str): Vessel to stop chilling. Name of the node the chiller is
            attached to.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'chiller': str
    }

    INTERNAL_PROPS = ['chiller']

    def __init__(self, vessel: str, chiller: str = None, **kwargs) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph):
        self.chiller = get_chiller(graph, self.vessel)

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.vessel, self.chiller], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        chempiler.acquire(self.chiller).stop()
        chempiler.release(self.chiller)
        return True

class CChillerSetTemp(ChemputerStep, AbstractBaseStep):
    """Sets the temperature setpoint.

    Args:
        vessel (str): Vessel to set chiller temperature. Name of the node the
            chiller is attached to.
        temp (float): Temperature in °C.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'temp': float,
        'chiller': str,
    }

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
    }

    INTERNAL_PROPS = ['chiller']

    def __init__(
        self,
        vessel: str,
        temp: float,
        chiller: str = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph):
        self.chiller = get_chiller(graph, self.vessel)

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.vessel, self.chiller], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object.
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        chempiler.acquire(self.chiller).set_temperature(temp=self.temp)
        chempiler.release(self.chiller)
        return True

class CChillerWaitForTemp(ChemputerStep, AbstractBaseStep):
    """Delays the script execution until the current temperature of the chiller
    is within 0.5°C of the setpoint.

    Args:
        vessel (str): Vessel to wait for temperature. Name of the node the
            chiller is attached to.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE
    }

    def __init__(self, vessel: str, **kwargs) -> None:
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.vessel], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object.
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        chempiler.chiller.wait_for_temp(self.vessel)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calcuates the duration of the step.

        Args:
            graph (MultiDiGraph): Chempuer graph to search.

        Returns:
            FTNDuration: Duration of the step.
        """
        # arbitrary value given for the moment
        return FTNDuration(0, 3600, 3600 * 3)


class CRampChiller(ChemputerStep, AbstractBaseStep):
    """Causes the chiller to ramp the temperature up or down. Only available for
    Petite Fleur.

    Args:
        vessel (str): Vessel to ramp chiller on. Name of the node the chiller
            is attached to.
        ramp_duration (int): Desired duration of the ramp in seconds.
        end_temperature (float): Final temperature of the ramp in °C.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'ramp_duration': int,
        'end_temperature': float,
        'chiller': str,
    }

    PROP_LIMITS = {
        'ramp_duration': TIME_PROP_LIMIT,
        'end_temperature': TEMP_PROP_LIMIT,
    }

    INTERNAL_PROPS = ['chiller']

    def __init__(
        self,
        vessel: str,
        ramp_duration: int,
        end_temperature: float,
        chiller: str = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph):
        self.chiller = get_chiller(graph, self.vessel)

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.vessel, self.chiller], [], []

    def sanity_checks(self, graph):
        return [SanityCheck(
            condition=graph.nodes[self.chiller]['class'] == HUBER_PETITE_FLEUR,
            error_msg='Ramp only available for Huber Petite Fleur chiller'
        )]

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object.
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        chiller = chempiler.acquire(self.chiller)

        chiller.set_ramp_duration(self.ramp_duration)
        chiller.start_ramp(self.end_temperature)

        chempiler.release(self.chiller)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calcuates the duration of thte step.

        Args:
            graph (MultiDiGraph): Chemputer graph to search

        Returns:
            FTNDuration: Duration of the step.
        """

        return FTNDuration(
            self.ramp_duration, self.ramp_duration, self.ramp_durations)

class CSetCoolingPower(ChemputerStep, AbstractBaseStep):
    """Sets the cooling power (0-100%). Only available for CF41.

    Args:
        vessel (str): Vessel to set cooling power of chiller. Name of the node
            the chiller is attached to.
        cooling_power (float): Desired cooling power in percent.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'cooling_power': float,
        'chiller': str
    }

    PROP_LIMITS = {
        'cooling_power': PERCENT_RANGE_PROP_LIMIT,
    }

    INTERNAL_PROPS = ['chiller']

    def __init__(
        self, vessel: str, cooling_power: float, chiller: str = None, **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph):
        self.chiller = get_chiller(graph, self.vessel)

    def sanity_checks(self, graph):
        return [
            SanityCheck(
                condition=graph.nodes[self.chiller]['class'] == JULABO_CF41,
                error_msg='Cooling power only available on Julabo CF41 chiller.'
            )
        ]

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.vessel, self.chiller], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object.
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        chempiler.acquire(self.chiller).set_cooling_power(self.cooling_power)
        chempiler.release(self.chiller)
        return True
