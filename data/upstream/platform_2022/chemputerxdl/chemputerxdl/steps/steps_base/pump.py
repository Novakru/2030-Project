"""
.. module:: steps_base.pump
    :platforms: Unix, Windows
    :synopsis: XDL Base steps for pump interaction

"""

from typing import Optional, Tuple, List
from networkx import MultiDiGraph

# XDL
from xdl.steps.utils import FTNDuration
from xdl.steps.base_steps import AbstractBaseStep
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from ..base_step import ChemputerStep
from ...utils.prop_limits import PORT_PROP_LIMIT
from ...constants import PORT_PROP_TYPE

class CSeparatePhases(ChemputerStep, AbstractBaseStep):
    """
    Separate two or more phases of liquid.

    Args:
        lower_phase_vessel (str): Name of vessel to transfer lower phase to.
        lower_phase_port (str): Name of port to transfer lower phase to
        upper_phase_vessel (str): Name of vessel to transfer upper phase to.
        separator_top (str): Name of separator top node in graph.
        separator_bottom (str): Name of separator bottom node in graph.
        dead_volume_target (str): Name of waste vessel to transfer dead
                                    volume between phases to.
    """

    PROP_TYPES = {
        'lower_phase_vessel': VESSEL_PROP_TYPE,
        'upper_phase_vessel': VESSEL_PROP_TYPE,
        'separation_vessel': VESSEL_PROP_TYPE,
        'dead_volume_target': VESSEL_PROP_TYPE,
        'lower_phase_port': PORT_PROP_TYPE,
        'upper_phase_port': PORT_PROP_TYPE,
        'dead_volume_port': PORT_PROP_TYPE,
        'lower_phase_through': str,
        'upper_phase_through': str,
        'dead_volume_through': str,
    }

    PROP_LIMITS = {
        'lower_phase_port': PORT_PROP_LIMIT,
        'upper_phase_port': PORT_PROP_LIMIT,
        'dead_volume_port': PORT_PROP_LIMIT,
    }

    DEFAULT_PROPS = {
        'lower_phase_port': None,
        'upper_phase_port': None,
        'dead_volume_port': None,
        'lower_phase_through': None,
        'upper_phase_through': None,
        'dead_volume_through': None,
    }

    def __init__(
        self,
        lower_phase_vessel: str,
        upper_phase_vessel: str,
        separation_vessel: str,
        dead_volume_target: str,
        lower_phase_port: Optional[str] = None,
        upper_phase_port: Optional[str] = None,
        dead_volume_port: Optional[str] = None,
        lower_phase_through: Optional[str] = None,
        upper_phase_through: Optional[str] = None,
        dead_volume_through: Optional[str] = None,
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

        vessel_locks = [
            self.lower_phase_vessel,
            self.upper_phase_vessel,
            self.separation_vessel,
            self.dead_volume_target
        ]
        return [vessel_locks], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # No need for acquire / release as all locking done within chempiler
        chempiler.pump.separate_phases(
            separator_flask=self.separation_vessel,
            lower_phase_target=self.lower_phase_vessel,
            lower_phase_port=self.lower_phase_port,
            lower_phase_through=self.lower_phase_through,
            upper_phase_target=self.upper_phase_vessel,
            upper_phase_port=self.upper_phase_port,
            upper_phase_through=self.upper_phase_through,
            dead_volume_target=self.dead_volume_target,
            dead_volume_port=self.dead_volume_port,
            dead_volume_through=self.dead_volume_through,
        )
        return True

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
