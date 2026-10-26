from typing import Tuple
import logging
from networkx import MultiDiGraph

from xdl.execution.client import XDLExecutionClient
from xdl.errors import XDLError
from xdl.platforms import AbstractPlatform
from chempiler import Chempiler
from chempiler.tools.errors import ChempilerError
import ChemputerAPI

from ..platform import ChemputerPlatform

def get_platform_controller_logger(
        logging_id: str, log_file: str) -> logging.Logger:
    """Get logger for Chempiler

    Args:
        logging_id (str): Unique ID to use for creating logger.
        log_file (str): File to send logs to.

    Returns:
        logging.Logger: Logger object that will log at level INFO to log_file.
    """
    platform_controller_logger = logging.getLogger(
        f'platform-controller-{logging_id}')

    platform_controller_handler = logging.FileHandler(log_file)
    platform_controller_formatter = logging.Formatter(
        'Platform controller: %(message)s')
    platform_controller_handler.setFormatter(platform_controller_formatter)
    platform_controller_handler.setLevel(logging.INFO)

    platform_controller_logger.setLevel(logging.INFO)
    platform_controller_logger.addHandler(platform_controller_handler)

    return platform_controller_logger


class ChemputerExecutionClient(XDLExecutionClient):
    """Chemputer execution client.

    Args:
        address (str): Address of ChemifyAPI.
    """

    def _get_platform(self) -> AbstractPlatform:
        return ChemputerPlatform()

    def _get_platform_controller(
        self, graph: MultiDiGraph, simulation: bool = False
    ) -> Tuple[Chempiler, str]:
        """Return Chempiler object with logging setup to send logs to default
        log file.

        Args:
            graph (str): Node link JSON graph to create platform controller with

        Returns:
            Tuple[Chempiler, str]:  Tuple of (Chempiler, error). If no error
                occurs during instantiation then error will be ''.
        """
        # If device already connected, disconnect before reinstantiating.
        if simulation is False and self._platform_controller is not None:
            self._platform_controller.disconnect()
            self._platform_controller = None

        try:
            # Create Chempiler
            platform_controller = Chempiler(
                experiment_code='execution-client',
                output_dir='.',
                simulation=simulation,
                graph_file=graph,
                device_modules=[ChemputerAPI]
            )

            # Add logger so that logs go to self.log_file
            logger = get_platform_controller_logger(
                self.execution_key, self._log_file)
            platform_controller.logger = logger
            platform_controller.pump.logger = logger
            platform_controller.vacuum.logger = logger
            platform_controller.chiller.logger = logger
            platform_controller.stirrer.logger = logger

            # Success, return Chempiler and empty error str.
            return platform_controller, ''

        # Error occurred, return None and error str
        except (XDLError, ChempilerError) as e:
            return None, str(e)

    def emergency_stop(self) -> None:
        """In the case of an emergency stop set the _pause flag to True so that
        no new steps try to execute, then disconnect from the Chempiler.
        """
        self._logger.info('Emergency stop!')
        self._pause = True
        self._platform_controller.disconnect()
