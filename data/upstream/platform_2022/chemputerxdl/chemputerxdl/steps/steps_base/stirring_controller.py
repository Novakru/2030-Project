from typing import Tuple, List, Callable
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import AbstractBaseStep
from xdl.utils.prop_limits import ROTATION_SPEED_PROP_LIMIT
from xdl.utils.misc import SanityCheck

# Relative
from ..base_step import ChemputerStep

NO_STIRRING_CONTROLLER_ERROR_MSG =\
    'Trying to stir but could not find device capable of stirring.'

class CStirringControllerStart(ChemputerStep, AbstractBaseStep):
    """Starts stirring.

    Args:
        stirring_controller (str): Node name of stirring controller.
    """

    PROP_TYPES = {
        'stirring_controller': str
    }

    def __init__(self, stirring_controller: str, **kwargs) -> None:
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

        return [self.stirring_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.stirring_controller,
                error_msg=NO_STIRRING_CONTROLLER_ERROR_MSG
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
        chempiler.acquire(self.stirring_controller).start_stirring()
        chempiler.release(self.stirring_controller)
        return True

class CStirringControllerStop(ChemputerStep, AbstractBaseStep):
    """Stops stirring.

    Args:
        stirring_controller (str): Node name of stirring controller.
    """

    PROP_TYPES = {
        'stirring_controller': str
    }

    def __init__(self, stirring_controller: str, **kwargs) -> None:
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

        return [self.stirring_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.stirring_controller,
                error_msg=NO_STIRRING_CONTROLLER_ERROR_MSG
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
        chempiler.acquire(self.stirring_controller).stop_stirring()
        chempiler.release(self.stirring_controller)
        return True

class CStirringControllerSetSpeed(ChemputerStep, AbstractBaseStep):
    """Sets stir rate.

    Args:
        stirring_controller (str): Node name of stirring controller.
        stir_speed (float): Stir speed to set stirring controller to.
    """

    PROP_TYPES = {
        'stirring_controller': str,
        'stir_speed': float,
    }

    PROP_LIMITS = {
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
    }

    def __init__(
        self,
        stirring_controller: str,
        stir_speed: float,
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

        return [self.stirring_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.stirring_controller,
                error_msg=NO_STIRRING_CONTROLLER_ERROR_MSG
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
        chempiler.acquire(self.stirring_controller).set_speed(self.stir_speed)
        chempiler.release(self.stirring_controller)
        return True

class CStirringControllerGetSpeed(ChemputerStep, AbstractBaseStep):
    """Gets current stir speed of stirring controller

    Args:
        stirring_controller (str): Node name of stirring controller.
        on_reading (str): Callback to handle stir speed reading.
    """

    PROP_TYPES = {
        'stirring_controller': str,
        'on_reading': Callable
    }

    def __init__(
        self,
        stirring_controller: str,
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

        return [self.stirring_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.stirring_controller,
                error_msg=NO_STIRRING_CONTROLLER_ERROR_MSG
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
        stirring_controller = chempiler.acquire(self.stirring_controller)
        self.on_reading(stirring_controller.get_speed())
        chempiler.release(self.stirring_controller)
        return True

class CStirringControllerGetSpeedSetpoint(ChemputerStep, AbstractBaseStep):
    """Gets current stir rate.

    Args:
        stirring_controller (str): Node name of stirring controller.
        on_reading (str): Callback to handle stir speed setpoint reading.
    """

    PROP_TYPES = {
        'stirring_controller': str,
        'on_reading': Callable
    }

    def __init__(
        self,
        stirring_controller: str,
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

        return [self.stirring_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.stirring_controller,
                error_msg=NO_STIRRING_CONTROLLER_ERROR_MSG
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
        stirring_controller = chempiler.acquire(self.stirring_controller)
        self.on_reading(stirring_controller.get_speed_setpoint())
        chempiler.release(self.stirring_controller)
        return True
