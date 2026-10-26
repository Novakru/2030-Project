"""
.. module:: steps_base.rotavap
    :platforms: Unix, Windows
    :synopsis: Base steps for the Chemputer Rotavaps

"""

from typing import Optional, Tuple, List, Callable
from networkx import MultiDiGraph

# XDL
from xdl.steps.utils import FTNDuration
from xdl.steps.base_steps import AbstractBaseStep
from xdl.utils.prop_limits import (
    TIME_PROP_LIMIT,
    PRESSURE_PROP_LIMIT,
    TEMP_PROP_LIMIT,
    PropLimit,
)
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from ..base_step import ChemputerStep

class CRotavapLiftUp(ChemputerStep, AbstractBaseStep):
    """Lifts the rotary evaporator arm up.

    Args:
        rotavap_name (str): Name of the node representing the rotary evaporator.
    """

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE
    }

    def __init__(self, rotavap_name: str, **kwargs) -> None:
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

        return [self.rotavap_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        rotavap = chempiler.acquire(self.rotavap_name)
        rotavap.lift_up()
        chempiler.release(self.rotavap_name)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Get the duration of the step.

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            FTNDuration: Duration of the step.
        """
        # Educated guess. Not measured.
        return FTNDuration(3, 5, 7)

class CRotavapLiftDown(ChemputerStep, AbstractBaseStep):
    """Lifts the rotary evaporator down.

    Args:
        rotavap_name (str): Name of the node representing the rotary evaporator.
    """

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE
    }

    def __init__(self, rotavap_name: str, **kwargs) -> None:
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

        return [self.rotavap_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        rotavap = chempiler.acquire(self.rotavap_name)
        rotavap.lift_down()
        chempiler.release(self.rotavap_name)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Get the duration of the step.

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            FTNDuration: Duration of the step.
        """

        # Educated guess. Not measured.
        return FTNDuration(3, 5, 7)

class CRotavapAutoEvaporation(ChemputerStep, AbstractBaseStep):
    """Perform the rotavap built-in auto-evaporation routine.

    Args:
        rotavap_name (str): Node name of the rotavap.
        sensitivity (int): Sensitivity mode to use. 0, 1 or 2 (Low, medium, high
            respectively).
        vacuum_limit (float): Minimum pressure for the process.
        time_limit (float): Maximum time to use for the process in seconds.
        vent_after (bool): If True, vacuum will be vented after the process is
            complete.
    """

    DEFAULT_PROPS = {
        'vent_after': True
    }

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE,
        'sensitivity': int,
        'vacuum_limit': float,
        'time_limit': float,
        'vent_after': bool
    }

    PROP_LIMITS = {
        'sensitivity': PropLimit(
            enum=['0', '1', '2'],
            default='0'
        ),
        'vacuum_limit': PRESSURE_PROP_LIMIT,
        'time_limit': TIME_PROP_LIMIT,
    }

    def __init__(
        self,
        rotavap_name: str,
        sensitivity: int,
        vacuum_limit: float,
        time_limit: float,
        vent_after: Optional[bool] = 'default',
        **kwargs
    ):
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

        return [self.rotavap_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # All locking done within chempiler
        chempiler.vacuum.auto_evaporation(
            node_name=self.rotavap_name,
            auto_mode=self.sensitivity,
            vacuum_limit=self.vacuum_limit,
            duration=self.time_limit,
            vent_after=self.vent_after
        )

        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculates duration of the step

        Args:
            graph (MultiDiGraph): Graph to search

        Returns:
            FTNDuration: Duration of step
        """
        # Educated guess. Not measured. Timeout on CVC3000 vacuum pump is
        # 30 mins so max value is empirical.
        return FTNDuration(10 * 60, 20 * 60, 30 * 60)

class CR300RotavapSetManualMode(ChemputerStep, AbstractBaseStep):
    """Sets the R300 rotavap up in manual mode.

    Args:
        rotavap_name (str): Node name of the rotavap.
    """

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE,
    }

    def __init__(self,
                 rotavap_name: str,
                 **kwargs
                 ):
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

        return [self.rotavap_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        rotavap = chempiler.acquire(self.rotavap_name)
        rotavap.set_mode('Manual')
        chempiler.release(self.rotavap_name)

        return True

class CR300RotavapSetAutoMode(ChemputerStep, AbstractBaseStep):
    """Sets the R300 rotavap up in 'AutoDest' mode.

    Args:
        rotavap_name (str): Node name of the rotavap.
    """

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE,
    }

    def __init__(self,
                 rotavap_name: str,
                 **kwargs
                 ):
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

        return [self.rotavap_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        rotavap = chempiler.acquire(self.rotavap_name)
        rotavap.set_mode('AutoDest')
        chempiler.release(self.rotavap_name)

        return True

class CR300RotavapStartChiller(ChemputerStep, AbstractBaseStep):
    """Sets the target temperature for the chiller of the
    R300 rotavap and starts the chiller.

    Args:
        rotavap_name (str): Node name of the rotavap.
        temp (float): Temperature set-point for the chiller.
    """
    DEFAULT_PROPS = {
        'temp': "5 °C",
    }

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE,
        'temp': float,
    }

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
    }

    def __init__(self,
                 rotavap_name: str,
                 temp: float = 'default',
                 **kwargs
                 ):
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

        return [self.rotavap_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        rotavap = chempiler.acquire(self.rotavap_name)
        rotavap.set_chiller_temperature(self.temp)
        rotavap.start_chiller()
        chempiler.release(self.rotavap_name)
        return True

class CR300RotavapGetChillerStatus(ChemputerStep, AbstractBaseStep):
    """Checks the current chiller temperature against the target temperature.

    Args:
        rotavap_name (str): Node name of the rotavap.
        on_reading (Callable): Callback function that processes
            the value returned form the rotavap chiller.
    """

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE,
        'on_reading': Callable,
    }

    def __init__(self,
                 rotavap_name: str,
                 on_reading: Callable,
                 **kwargs
                 ):
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

        return [self.rotavap_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        rotavap = chempiler.acquire(self.rotavap_name)
        self.on_reading(current_temp=rotavap.get_chiller_temperature(),
                        target_temp=rotavap.get_chiller_temperature_setpoint())
        chempiler.release(self.rotavap_name)
        return True

class CR300RotavapGetStatus(ChemputerStep, AbstractBaseStep):
    """Retrieves the status of the R300 rotary evaporator.

    Args:
        rotavap_name (str): Node name of the rotavap.
        on_reading (Callable): Callback function that processes
            the value returned form the rotavap.
    """
    DEFAULT_PROPS = {
    }

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE,
        'on_reading': Callable,
    }

    def __init__(self,
                 rotavap_name: str,
                 on_reading: Callable,
                 **kwargs
                 ):
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

        return [self.rotavap_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        rotavap = chempiler.acquire(self.rotavap_name)
        self.on_reading(rotavap.is_idle())
        chempiler.release(self.rotavap_name)
        return True

class CRotavapStart(ChemputerStep, AbstractBaseStep):
    """Start rotary evaporator. Vacuum, bath heating, lift arm down and chiller
    is present.

    Args:
        rotavap_name (str): Name of the node representing the rotary evaporator.
    """

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE
    }

    def __init__(self, rotavap_name: str, **kwargs) -> None:
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

        return [self.rotavap_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        rotavap = chempiler.acquire(self.rotavap_name)
        rotavap.start()
        chempiler.release(self.rotavap_name)
        return True

class CRotavapStop(ChemputerStep, AbstractBaseStep):
    """Stop rotary evaporator. Stop vacuum, bath heating, lift arm up and stop
    chiller if present.

    Args:
        rotavap_name (str): Name of the node representing the rotary evaporator.
    """

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE
    }

    def __init__(self, rotavap_name: str, **kwargs) -> None:
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

        return [self.rotavap_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        rotavap = chempiler.acquire(self.rotavap_name)
        rotavap.stop()
        chempiler.release(self.rotavap_name)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Get the duration of the step.

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            FTNDuration: Duration of the step.
        """

        # Educated guess. Not measured.
        return FTNDuration(3, 5, 10)
