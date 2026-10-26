from typing import Tuple, List, Callable
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import AbstractBaseStep
from xdl.utils.prop_limits import TEMP_PROP_LIMIT
from xdl.utils.misc import SanityCheck

# Relative
from ..base_step import ChemputerStep
from ...utils.execution import (
    get_node_temp_range,
    get_temperature_controller_sensor,
    convert_sensor_type_to_pylabware2_code
)
from ...utils.prop_limits import (
    TEMP_SENSOR_PROP_LIMIT, TEMP_SENSOR_CODE_PROP_LIMIT)

NO_TEMPERATURE_CONTROLLER_ERROR_MSG =\
    'Trying to control temperature but could not find device capable of\
temperature regulation.'

class CTemperatureControllerStart(ChemputerStep, AbstractBaseStep):
    """Starts temperature control.

    Args:
        temperature_controller (str): Node name of temperature controller.
    """

    PROP_TYPES = {
        'temperature_controller': str
    }

    def __init__(self, temperature_controller: str, **kwargs) -> None:
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

        return [self.temperature_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.temperature_controller,
                error_msg=NO_TEMPERATURE_CONTROLLER_ERROR_MSG
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
        chempiler.acquire(
            self.temperature_controller).start_temperature_regulation()
        chempiler.release(self.temperature_controller)
        return True

class CTemperatureControllerStop(ChemputerStep, AbstractBaseStep):
    """Stops temperature control.

    Args:
        temperature_controller (str): Node name of temperature controller.
    """

    PROP_TYPES = {
        'temperature_controller': str
    }

    def __init__(self, temperature_controller: str, **kwargs) -> None:
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

        return [self.temperature_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.temperature_controller,
                error_msg=NO_TEMPERATURE_CONTROLLER_ERROR_MSG
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

        chempiler.acquire(
            self.temperature_controller).stop_temperature_regulation()
        chempiler.release(self.temperature_controller)
        return True

class CTemperatureControllerSetTemp(ChemputerStep, AbstractBaseStep):
    """Sets target temperature.

    Args:
        temperature_controller (str): Node name of temperature controller.
        temp (float): Temperature to set temperature controller to.
    """

    PROP_TYPES = {
        'temperature_controller': str,
        'temp': float,
        'sensor': str,
        'sensor_code': int,
    }

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'sensor': TEMP_SENSOR_PROP_LIMIT,
        'sensor_code': TEMP_SENSOR_CODE_PROP_LIMIT,
    }

    INTERNAL_PROPS = ['sensor', 'sensor_code']

    def __init__(
        self,
        temperature_controller: str,
        temp: float,
        sensor: str = None,
        sensor_code: int = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        self.sensor = get_temperature_controller_sensor(
            graph, self.temperature_controller)
        self.sensor_code = convert_sensor_type_to_pylabware2_code(self.sensor)

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

        return [self.temperature_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        temp_controller_min_temp, temp_controller_max_temp =\
            get_node_temp_range(graph, self.temperature_controller)
        return [
            SanityCheck(
                condition=self.temperature_controller,
                error_msg=NO_TEMPERATURE_CONTROLLER_ERROR_MSG
            ),
            SanityCheck(
                condition=(
                    temp_controller_min_temp
                    <= self.temp
                    <= temp_controller_max_temp
                ),
                error_msg=f"Temperature controller\
 '{self.temperature_controller}' is unable to go to temp {self.temp}°C.\
 Valid temp range: {temp_controller_min_temp} to {temp_controller_max_temp}°C."
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
        temperature_controller = chempiler.acquire(self.temperature_controller)
        temperature_controller.set_temperature(self.temp, self.sensor_code)
        chempiler.release(self.temperature_controller)
        return True

class CTemperatureControllerGetTemp(ChemputerStep, AbstractBaseStep):
    """Gets current temperature.

    Args:
        temperature_controller (str): Node name of temperature controller.
        on_reading (str): Callback to handle temperature reading.
    """

    PROP_TYPES = {
        'temperature_controller': str,
        'on_reading': Callable,
        'sensor': str,
        'sensor_code': int,
    }

    PROP_LIMITS = {
        'sensor': TEMP_SENSOR_PROP_LIMIT,
        'sensor_code': TEMP_SENSOR_CODE_PROP_LIMIT,
    }

    INTERNAL_PROPS = ['sensor', 'sensor_code']

    def __init__(
        self,
        temperature_controller: str,
        on_reading: Callable,
        sensor: str = None,
        sensor_code: int = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        self.sensor = get_temperature_controller_sensor(
            graph, self.temperature_controller)
        self.sensor_code = convert_sensor_type_to_pylabware2_code(self.sensor)

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

        return [self.temperature_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.temperature_controller,
                error_msg=NO_TEMPERATURE_CONTROLLER_ERROR_MSG
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
        temperature_controller = chempiler.acquire(self.temperature_controller)
        self.on_reading(
            temperature_controller.get_temperature(self.sensor_code))
        chempiler.release(self.temperature_controller)
        return True

class CTemperatureControllerGetTempSetpoint(ChemputerStep, AbstractBaseStep):
    """Gets current target temperature.

    Args:
        temperature_controller (str): Node name of temperature controller.
        on_reading (str): Callback to handle temperature setpoint reading.
    """

    PROP_TYPES = {
        'temperature_controller': str,
        'on_reading': Callable,
        'sensor': str,
        'sensor_code': int,
    }

    INTERNAL_PROPS = ['sensor', 'sensor_code']

    def __init__(
        self,
        temperature_controller: str,
        on_reading: Callable,
        sensor: str = None,
        sensor_code: int = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        self.sensor = get_temperature_controller_sensor(
            graph, self.temperature_controller)
        self.sensor_code = convert_sensor_type_to_pylabware2_code(self.sensor)

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

        return [self.temperature_controller], [], []

    def sanity_checks(self, graph: MultiDiGraph) -> None:
        return [
            SanityCheck(
                condition=self.temperature_controller,
                error_msg=NO_TEMPERATURE_CONTROLLER_ERROR_MSG
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
        temperature_controller = chempiler.acquire(self.temperature_controller)
        self.on_reading(
            temperature_controller.get_temperature_setpoint(self.sensor_code))
        chempiler.release(self.temperature_controller)
        return True
