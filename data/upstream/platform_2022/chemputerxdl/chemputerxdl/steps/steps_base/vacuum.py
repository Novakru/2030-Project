"""
.. module:: steps_base.vacuum
    :platforms: Unix, Windows
    :synopsis: Base steps for Chemputer Vacuum lines

"""

from typing import List, Tuple
from networkx import MultiDiGraph

# XDL
from xdl.steps.utils import FTNDuration
from xdl.steps.base_steps import AbstractBaseStep
from xdl.utils.prop_limits import (
    PRESSURE_PROP_LIMIT,
    TIME_PROP_LIMIT,
    PERCENT_RANGE_PROP_LIMIT
)
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from ..base_step import ChemputerStep


class CGetVacuumSetPoint(ChemputerStep, AbstractBaseStep):
    """Reads the current vacuum setpoint.

    Args:
        vessel (str): Name of the node the vacuum pump is attached to.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
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
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # Locking handled within chempiler
        chempiler.vacuum.get_vacuum_set_point(self.vessel)
        return True

class CSetVacuumSetPoint(ChemputerStep, AbstractBaseStep):
    """Sets a new vacuum setpoint.

    Args:
        vessel (str): Name of the node the vacuum pump is attached to.
        vacuum_pressure (float): Vacuum pressure setpoint in mbar.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'vacuum_pressure': float
    }

    PROP_LIMITS = {
        'vacuum_pressure': PRESSURE_PROP_LIMIT,
    }

    def __init__(self, vessel: str, vacuum_pressure: float, **kwargs) -> None:
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
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # Locking handled within chempiler
        chempiler.vacuum.set_vacuum_set_point(
            self.vessel, self.vacuum_pressure
        )

        return True

class CStartVacuum(ChemputerStep, AbstractBaseStep):
    """Starts the vacuum pump.

    Args:
        vessel (str): Name of the node the vacuum pump is attached to.
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
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # Locking handled within chempiler
        chempiler.vacuum.start_vacuum(self.vessel)
        return True

class CStopVacuum(ChemputerStep, AbstractBaseStep):
    """Stops the vacuum pump.

    Args:
        vessel (str): Name of the node the vacuum pump is attached to.
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
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # Locking handled within chempiler
        chempiler.vacuum.stop_vacuum(self.vessel)
        return True

class CVentVacuum(ChemputerStep, AbstractBaseStep):
    """Vents the vacuum pump to ambient pressure.

    Args:
        vessel (str): Name of the node the vacuum pump is attached to.
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
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # Locking handled within chempiler
        chempiler.vacuum.vent_vacuum(self.vessel)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Get the duration of the step.

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            FTNDuration: Duration of the step
        """

        # Educated guess. Not measured.
        return FTNDuration(5, 10, 30)


class CSetSpeedSetPoint(ChemputerStep, AbstractBaseStep):
    """Sets the speed of the vacuum pump (0-100%).

    Args:
        vessel (str): Name of the node the vacuum pump is attached to.
        vacuum_pump_speed (float): Vacuum pump speed in percent.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'vacuum_pump_speed': float
    }

    PROP_LIMITS = {
        'vacuum_pump_speed': PERCENT_RANGE_PROP_LIMIT,
    }

    def __init__(self, vessel: str, vacuum_pump_speed: float, **kwargs) -> None:
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
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # Locking handled within chempiler
        chempiler.vacuum.set_speed_set_point(self.vessel, self.set_point)
        return True

class CSetEndVacuumSetPoint(ChemputerStep, AbstractBaseStep):
    """
    Sets the switch off vacuum set point.

    Args:
        vessel (str): Name of the node the vacuum pump is attached to.
        vacuum_set_point (int): Set point value to set vacuum to.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'vacuum_set_point': int
    }

    PROP_LIMITS = {
        'vacuum_set_point': PRESSURE_PROP_LIMIT,
    }

    def __init__(self, vessel: str, vacuum_set_point: int, **kwargs) -> None:
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
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # Locking handled within chempiler
        chempiler.vacuum.set_end_vacuum_set_point(
            self.vessel, self.vacuum_set_point
        )

        return True

class CGetEndVacuumSetPoint(ChemputerStep, AbstractBaseStep):
    """
    Gets the set point (target) for the switch off vacuum in mode Auto.

    Args:
        vessel (str): Name of the node the vacuum pump is attached to.
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
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # Locking handled within chempiler
        chempiler.vacuum.get_end_vacuum_set_point(self.vessel)
        return True

class CSetRuntimeSetPoint(ChemputerStep, AbstractBaseStep):
    """
    Sets the switch off vacuum set point.

    Args:
        vessel (str): Name of the node the vacuum pump is attached to.
        time (float): Desired runtime.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'time': float
    }

    PROP_LIMITS = {
        'time': TIME_PROP_LIMIT,
    }

    def __init__(self, vessel: str, time: float, **kwargs) -> None:
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
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # Locking handled within chempiler
        chempiler.vacuum.set_runtime_set_point(self.vessel, self.time)
        return True

class CGetRuntimeSetPoint(ChemputerStep, AbstractBaseStep):
    """
    Gets the set point (target) for the run time in mode Auto.

    Args:
        vessel (str): Name of the node the vacuum pump is attached to.
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
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # Locking handled within chempiler
        chempiler.vacuum.get_runtime_set_point(self.vessel)
        return True
