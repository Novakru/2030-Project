"""
.. module:: steps_utility.cleaning
    :platforms: Unix, Windows
    :synopsis: XDL steps related to cleaning the Chemputer backbone

"""

from typing import Optional, List
from networkx import MultiDiGraph
from xdl.steps import AbstractStep, Step
from xdl.steps.templates import AbstractResetHandlingStep
from xdl.utils.prop_limits import VOLUME_PROP_LIMIT
from xdl.constants import REAGENT_PROP_TYPE
from ..base_step import ChemputerStep
from ..steps_base import CMove
from ...constants import (
    DEFAULT_CLEAN_BACKBONE_VOLUME, CHEMPUTER_WASTE)
from ...utils.execution import (
    get_reagent_vessel, get_waste_on_valve, get_backbone
)
from xdl.errors import XDLError
from xdl.utils.misc import SanityCheck

class CleanBackboneDeprecated(ChemputerStep, AbstractStep):
    """
    This step just moves 3 mL solvent to all waste vessels in the rig.

    NOTE::DEPRECATED STEP
    """

    INTERNAL_PROPS = [
        'waste_vessels',
        'solvent_vessel',
    ]

    PROP_TYPES = {
        'solvent': REAGENT_PROP_TYPE,
        'waste_vessels': List[str],
        'solvent_vessel': str
    }

    def __init__(
        self,
        solvent: str,

        # Internal properties
        waste_vessels: Optional[List[str]] = [],
        solvent_vessel: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Obtain solvent vessel if not defined
        if not self.solvent_vessel:
            self.solvent_vessel = get_reagent_vessel(graph, self.solvent)

        # Obtain list of waste vessel if not defined
        if not self.waste_vessels:
            self.waste_vessels = [
                node for node, data in graph.nodes(data=True)
                if data['class'] == CHEMPUTER_WASTE
            ]

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        return [
            CMove(
                from_vessel=self.solvent_vessel,
                to_vessel=waste_vessel,
                volume=DEFAULT_CLEAN_BACKBONE_VOLUME
            )
            for waste_vessel in self.waste_vessels
        ]

class ResetHandling(ChemputerStep, AbstractResetHandlingStep):
    """This step directly wraps `CleanBackbone`. `CleanBackbone` is kept just
    for backwards compatibility with XDL procedures that use `CleanBackbone`
    explicitly.

    Clean backbone by pushing solvent to end valves on backbone. The choice
    of 3 cleans was chosen as this was shown to be more effective and faster
    than the previous backbone cleaning process of moving solvent to all waste
    vessels (using UV absorbance measurements of a dye).

    NOTE: The words 'near' and 'far' are used in this step just to describe
          the two distinct ends of the backbone. The 'near' end is not
          necessarily 'nearer' to the solvent valve. 'near' should be the
          leftmost valve on the graph and 'far' the rightmost.

    Arguments:
        solvent (str): Solvent to clean with.
        n_cleans (int): Number of times to push solvent to each end of the
            backbone.
        volume (float): Volume of solvent to push to each end of the backbone,
            each time.
        near_waste (str): Waste on one end of the backbone.
        far_waste (str): Waste on other end of the backbone.
        solvent_waste (str): Waste on valve connected to solvent vessel.
        solvent_vessel (str): Vessel containing solvent.
    """

    PROP_TYPES = {
        'solvent': REAGENT_PROP_TYPE,
        'repeats': int,
        'volume': float,
    }

    DEFAULT_PROPS = {
        'solvent': None,
        'repeats': 3,
        'volume': '3 mL',
    }

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
    }

    def __init__(
        self,
        solvent: Optional[str] = 'default',
        repeats: Optional[int] = 'default',
        volume: Optional[float] = 'default',
        **kwargs
    ):
        super().__init__(locals())

    def get_steps(self):
        return [
            CleanBackbone(
                solvent=self.solvent,
                n_cleans=self.repeats,
                volume=self.volume,
            )
        ]

class CleanBackbone(ChemputerStep, AbstractStep):
    """Clean backbone by pushing solvent to end valves on backbone. The choice
    of 3 cleans was chosen as this was shown to be more effective and faster
    than the previous backbone cleaning process of moving solvent to all waste
    vessels (using UV absorbance measurements of a dye).

    NOTE: The words 'near' and 'far' are used in this step just to describe
          the two distinct ends of the backbone. The 'near' end is not
          necessarily 'nearer' to the solvent valve. 'near' should be the
          leftmost valve on the graph and 'far' the rightmost.

    Arguments:
        solvent (str): Solvent to clean with.
        n_cleans (int): Number of times to push solvent to each end of the
            backbone.
        volume (float): Volume of solvent to push to each end of the backbone,
            each time.
        near_waste (str): Waste on one end of the backbone.
        far_waste (str): Waste on other end of the backbone.
        solvent_waste (str): Waste on valve connected to solvent vessel.
        solvent_vessel (str): Vessel containing solvent.
    """

    PROP_TYPES = {
        'solvent': REAGENT_PROP_TYPE,
        'near_waste': str,
        'far_waste': str,
        'solvent_waste': str,
        'solvent_vessel': str,
        'solvent_valve': str,
        'n_cleans': int,
        'volume': float,
    }

    DEFAULT_PROPS = {
        'n_cleans': 3,
        'volume': '3 mL',
    }

    INTERNAL_PROPS = [
        'near_waste',
        'far_waste',
        'solvent_waste',
        'solvent_vessel',
        'solvent_valve',
    ]

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
    }

    def __init__(
        self,
        solvent: str,
        n_cleans: Optional[int] = 'default',
        volume: Optional[float] = 'default',

        # Internal properties
        near_waste: Optional[str] = None,
        far_waste: Optional[str] = None,
        solvent_waste: Optional[str] = None,
        solvent_valve: Optional[str] = None,
        solvent_vessel: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check

        Raises:
            XDLError: Cannot find the near or far end of the backbone
        """

        # Get solvent flask and waste
        self.solvent_vessel = get_reagent_vessel(graph, self.solvent)
        self.solvent_waste = get_waste_on_valve(graph, self.solvent_vessel)

        # Get the backbone
        backbone = get_backbone(graph, ordered=True)

        # Get wastes on end of backbone
        if len(backbone) == 1:
            self.near_waste = get_waste_on_valve(graph, backbone[0])
            self.far_waste = self.near_waste
        elif len(backbone) > 1:
            self.near_waste = get_waste_on_valve(graph, backbone[0])
            self.far_waste = get_waste_on_valve(graph, backbone[-1])

        # Cannot find the backbone
        else:
            raise XDLError(
                f"Can't find backbone.\n{backbone}")

        # Cannot find the ends of the backbone
        if not self.near_waste:
            raise XDLError('Cannot find waste on left end of backbone.')
        if not self.far_waste:
            raise XDLError('Cannot find waste on right end of backbone.')

    def sanity_checks(self, graph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        sanity_checks = [
            SanityCheck(
                condition=self.solvent_vessel,
                error_msg=f'Cannot find vessel containing "{self.solvent}"'
            ),

            SanityCheck(
                condition=self.volume > 0,
                error_msg=f'Volume ({self.volume} mL) must be > 0.'
            ),

            SanityCheck(
                condition=self.n_cleans,
                error_msg=f'Number of cleans ({self.n_cleans}) must be > 0.'
            ),

            SanityCheck(
                condition=self.far_waste,
                error_msg='Cannot find waste on right end of backbone.'
            ),

            SanityCheck(
                condition=self.near_waste,
                error_msg='Cannot find waste on left end of backbone.'
            )
        ]

        return sanity_checks

    def get_steps(self) -> Optional[List[Step]]:
        """Get the list of steps/base steps to execute.

        Returns:
            Optional[List[Step]]: Steps to execute, none if no steps found
        """

        # No waste attached to solvent valve so use near and far waste if
        # available.
        if not self.solvent_waste:
            if self.near_waste:
                if self.far_waste:
                    if self.near_waste != self.far_waste:
                        return self.get_near_and_far_clean_steps()

                    else:
                        return self.get_near_clean_steps()

                else:
                    self.get_near_clean_steps()

            elif self.far_waste:
                return self.get_far_clean_steps()

        # Waste attached to solvent valve so don't push to this waste if it is
        # also the near or far waste.
        else:
            if self.solvent_waste != self.far_waste:
                if self.solvent_waste != self.near_waste:

                    if self.near_waste != self.far_waste:
                        # Solvent waste is not near or far waste
                        return self.get_near_and_far_clean_steps()

                    else:
                        return self.get_near_clean_steps()

                else:

                    # Solvent waste is near waste
                    return self.get_far_clean_steps()

            else:
                if self.solvent_waste != self.near_waste:

                    # Solvent waste is far waste
                    return self.get_near_clean_steps()
                else:

                    # Solvent waste is both near and far waste.
                    return self.get_near_clean_steps()

        return []

    def get_near_and_far_clean_steps(self) -> List[Step]:
        """Move to both ends of backbone.

        Returns:
            List[Step]: Movement steps to both ends of the backbone
        """

        return self.get_far_clean_steps() + self.get_near_clean_steps()

    def get_near_clean_steps(self) -> List[Step]:
        """Move to near end of the backbone.

        Returns:
            List[Step]: Movement steps to the near end of the backbone
        """

        return [
            CMove(
                from_vessel=self.solvent_vessel,
                to_vessel=self.near_waste,
                volume=self.volume,
                repeats=self.n_cleans,
            )
        ]

    def get_far_clean_steps(self) -> List[Step]:
        """Move to far end of the backbone.

        Returns:
            List[Step]: Movement steps to the far end of the backbone
        """

        return [
            CMove(
                from_vessel=self.solvent_vessel,
                to_vessel=self.far_waste,
                volume=self.volume,
                repeats=self.n_cleans,
            )
        ]
