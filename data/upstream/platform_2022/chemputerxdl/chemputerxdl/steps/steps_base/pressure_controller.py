"""
.. module:: steps_base.stirrer
    :platforms: Unix, Windows
    :synopsis: Base steps for the Chemputer stirrers

"""

from networkx import MultiDiGraph
from typing import Tuple, List, Callable

# XDL
from xdl.steps.base_steps import AbstractBaseStep
from xdl.utils.prop_limits import PRESSURE_PROP_LIMIT
from xdl.utils.misc import SanityCheck

# Relative
from ..base_step import ChemputerStep

NO_PRESSURE_CONTROLLER_ERROR_MSG =\
    'Trying to control pressure but could not find device capable of\
pressure regulation.'

class CPressureControllerStart(ChemputerStep, AbstractBaseStep):
    """Starts pressure control.

    Args:
        pressure_controller (str): Node name of pressure controller.
    """

    PROP_TYPES = {
        'pressure_controller': str
    }

    def __init__(self, pressure_controller: str, **kwargs) -> None:
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

        return [self.pressure_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.pressure_controller,
                error_msg=NO_PRESSURE_CONTROLLER_ERROR_MSG
            )
        ]

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        chempiler.acquire(self.pressure_controller).start_pressure_regulation()
        chempiler.release(self.pressure_controller)
        return True

class CPressureControllerStop(ChemputerStep, AbstractBaseStep):
    """Stops pressure control.

    Args:
        pressure_controller (str): Node name of pressure controller.
    """

    PROP_TYPES = {
        'pressure_controller': str
    }

    def __init__(self, pressure_controller: str, **kwargs) -> None:
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

        return [self.pressure_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.pressure_controller,
                error_msg=NO_PRESSURE_CONTROLLER_ERROR_MSG
            )
        ]

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        chempiler.acquire(self.pressure_controller).stop_pressure_regulation()
        chempiler.release(self.pressure_controller)
        return True

class CPressureControllerSetPressure(ChemputerStep, AbstractBaseStep):
    """Sets target pressure.

    Args:
        pressure_controller (str): Node name of pressure controller.
        pressure (float): Pressure to set pressure controller to.
    """

    PROP_TYPES = {
        'pressure_controller': str,
        'pressure': float,
    }

    PROP_LIMITS = {
        'pressure': PRESSURE_PROP_LIMIT,
    }

    def __init__(
            self, pressure_controller: str, pressure: float, **kwargs) -> None:
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

        return [self.pressure_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.pressure_controller,
                error_msg=NO_PRESSURE_CONTROLLER_ERROR_MSG
            )
        ]

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        chempiler.acquire(self.pressure_controller).set_pressure(self.pressure)
        chempiler.release(self.pressure_controller)
        return True

class CPressureControllerGetPressure(ChemputerStep, AbstractBaseStep):
    """Gets current pressure.

    Args:
        pressure_controller (str): Node name of pressure controller.
        on_reading (str): Callback to handle pressure reading.
    """

    PROP_TYPES = {
        'pressure_controller': str,
        'on_reading': Callable
    }

    def __init__(
        self,
        pressure_controller: str,
        on_reading: Callable,
        **kwargs
    ) -> None:
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

        return [self.pressure_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.pressure_controller,
                error_msg=NO_PRESSURE_CONTROLLER_ERROR_MSG
            )
        ]

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        pressure_controller = chempiler.acquire(self.pressure_controller)
        self.on_reading(pressure_controller.get_pressure())
        chempiler.release(self.pressure_controller)
        return True

class CPressureControllerGetPressureSetpoint(ChemputerStep, AbstractBaseStep):
    """Gets current target pressure.

    Args:
        pressure_controller (str): Node name of pressure controller.
        on_reading (str): Callback to handle pressure setpoint reading.
    """

    PROP_TYPES = {
        'pressure_controller': str,
        'on_reading': Callable
    }

    def __init__(
        self,
        pressure_controller: str,
        on_reading: Callable,
        **kwargs
    ) -> None:
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

        return [self.pressure_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.pressure_controller,
                error_msg=NO_PRESSURE_CONTROLLER_ERROR_MSG
            )
        ]

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        pressure_controller = chempiler.acquire(self.pressure_controller)
        self.on_reading(pressure_controller.get_pressure_setpoint())
        chempiler.release(self.pressure_controller)
        return True

class CPressureControllerVentOn(ChemputerStep, AbstractBaseStep):
    """Start venting pressure controller.

    Args:
        pressure_controller (str): Node name of pressure controller.
    """

    PROP_TYPES = {
        'pressure_controller': str
    }

    def __init__(self, pressure_controller: str, **kwargs) -> None:
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

        return [self.pressure_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.pressure_controller,
                error_msg=NO_PRESSURE_CONTROLLER_ERROR_MSG
            )
        ]

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        chempiler.acquire(self.pressure_controller).vent_on()
        chempiler.release(self.pressure_controller)
        return True

class CPressureControllerVentOff(ChemputerStep, AbstractBaseStep):
    """Stop venting pressure controller.

    Args:
        pressure_controller (str): Node name of pressure controller.
    """

    PROP_TYPES = {
        'pressure_controller': str
    }

    def __init__(self, pressure_controller: str, **kwargs) -> None:
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

        return [self.pressure_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.pressure_controller,
                error_msg=NO_PRESSURE_CONTROLLER_ERROR_MSG
            )
        ]

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        chempiler.acquire(self.pressure_controller).vent_off()
        chempiler.release(self.pressure_controller)
        return True
