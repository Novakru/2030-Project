"""
... module:: steps_synthesis.filter_through
    :platforms: Unix, Windows
    :synopsis: XDL step for filtering through a filter or cartridge

"""

import math
from typing import Optional, List
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import Step
from xdl.steps.templates import AbstractFilterThroughStep
from xdl.steps.special_steps import Repeat
from xdl.utils.misc import SanityCheck
from xdl.utils.prop_limits import VOLUME_PROP_LIMIT, TIME_PROP_LIMIT
from xdl.constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE

# Relative
from .clean_vessel import CleanVessel
from ..base_step import ChemputerStep
from ..steps_utility import Transfer
from ...utils.execution import (
    get_reagent_vessel, get_flush_tube_vessel, get_cartridge, get_buffer_flask)

class FilterThrough(ChemputerStep, AbstractFilterThroughStep):
    """Filter contents of from_vessel through a cartridge,
    e.g. a Celite cartridge, and optionally elute with a solvent as well.

    Args:
        from_vessel (str): Vessel with contents to filter.
        to_vessel (str): Vessel to pass filtered contents to.
        through (str): Substrate to pass from_vessel contents through. Either
            this or through_cartridge must be given.
        eluting_solvent (str): Solvent to elute with after filtering.
        eluting_volume (float): Volume of solvent to elute with after filtering.
        eluting_repeats (float): Number of times to elute with eluting_solvent
            and eluting_volume. Defaults to 1.
        move_speed (float): Move speed in mL / min.
        aspiration_speed (float): Aspiration speed in mL / min.
        eluting_solvent_vessel (str): Given internally. Flask containing eluting
            solvent.
        flush_cartridge_vessel (str): Given internally. Flask to flush dead
            volume of cartridge with after main transfers are done. Order of
            preference is nitrogen > air > nothing.
        cartridge_dead_volume (float): Volume of gas to push through if flushing
            cartridge dead volume.
        through_cartridge (str): Internal property. Cartridge to pass
            from_vessel contents through.
        buffer_flask (str): Given internally. If from_vessel and to_vessel are
            the same buffer_flask will be used to push contents of from_vessel
            to temporarily, before moving to to_vessel.
    """

    DEFAULT_PROPS = {
        'eluting_solvent': None,
        'eluting_volume': '10 mL',
        'move_speed': 5,  # mL / min
        'aspiration_speed': 5,  # mL / min
        'eluting_repeats': 1,
        'cartridge_dead_volume': '25 mL',
        'through': None,
        'residence_time': None,
    }

    PROP_TYPES = {
        'from_vessel': VESSEL_PROP_TYPE,
        'to_vessel': VESSEL_PROP_TYPE,
        'through': str,
        'eluting_solvent': REAGENT_PROP_TYPE,
        'eluting_volume': float,
        'eluting_repeats': int,
        'residence_time': float,
        'move_speed': float,
        'aspiration_speed': float,
        'eluting_solvent_vessel': str,
        'flush_cartridge_vessel': str,
        'through_cartridge': str,
        'cartridge_dead_volume': float,
        'buffer_flask': str,
        'from_vessel_max_volume': float
    }

    INTERNAL_PROPS = [
        'eluting_solvent_vessel',
        'flush_cartridge_vessel',
        'through_cartridge',
        'cartridge_dead_volume',
        'buffer_flask',
        'from_vessel_max_volume',
    ]

    PROP_LIMITS = {
        'eluting_volume': VOLUME_PROP_LIMIT,
        'cartridge_dead_volume': VOLUME_PROP_LIMIT,
        'from_vessel_max_volume': VOLUME_PROP_LIMIT,
        'residence_time': TIME_PROP_LIMIT,
    }

    def __init__(
        self,
        from_vessel: str,
        to_vessel: str,
        through: Optional[str] = 'default',
        eluting_solvent: Optional[str] = 'default',
        eluting_volume: Optional[float] = 'default',
        eluting_repeats: Optional[int] = 'default',
        move_speed: Optional[float] = 'default',
        aspiration_speed: Optional[float] = 'default',
        residence_time: Optional[float] = 'default',

        # Internal properties
        eluting_solvent_vessel: Optional[str] = None,
        flush_cartridge_vessel: Optional[str] = None,
        through_cartridge: Optional[str] = None,
        cartridge_dead_volume: Optional[float] = 'default',
        buffer_flask: Optional[str] = None,
        from_vessel_max_volume: Optional[float] = None,
        **kwargs
    ):
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Obtain buffer flask if not already defined
        if not self.buffer_flask:
            self.buffer_flask = get_buffer_flask(
                graph, self.from_vessel, return_single=True
            )

        # Obtian the eluting solvent vessel if not already defined
        if self.eluting_solvent:
            if not self.eluting_solvent_vessel:
                self.eluting_solvent_vessel = get_reagent_vessel(
                    graph, self.eluting_solvent
                )

        # Obtian the flush cartridge vessel if not already defined
        if not self.flush_cartridge_vessel:
            self.flush_cartridge_vessel = get_flush_tube_vessel(
                graph, self.to_vessel
            )

        # Obtian the vessel's maximum volume if not already defined
        if not self.from_vessel_max_volume:
            self.from_vessel_max_volume = graph.nodes[
                self.from_vessel
            ]['max_volume']

        # Obtain the through cartidge if not already defined
        if not self.through_cartridge:
            self.through_cartridge = get_cartridge(graph, self.through)

        # Obtain the cartridge dead volume from the graph information if set
        if not self.cartridge_dead_volume:
            cartridge = graph.nodes[self.through_cartridge]
            if 'dead_volume' in cartridge:
                self.cartridge_dead_volume = cartridge['dead_volume']

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        # Get the maximum volume fo the to_vessel from the graph
        to_vessel_max_volume = graph.nodes[self.to_vessel]['max_volume']

        # Create list of initial checks
        checks = [
            SanityCheck(
                condition=(self.from_vessel != self.to_vessel
                           or self.buffer_flask),
                error_msg='Trying to filter through cartridge to and from the same\
 vessel, but cannot find buffer flask to use.'
            ),

            SanityCheck(
                condition=self.through_cartridge,
                error_msg=f'Trying to filter through "{self.through}" but cannot find\
 cartridge containing {self.through}.'
            ),

        ]

        # Extend checks if the eluting solvent is defined
        if self.eluting_solvent:
            checks.extend([
                SanityCheck(
                    condition=self.eluting_solvent_vessel,
                    error_msg=f'"{self.eluting_solvent}" specified as eluting solvent but\
 no vessel found containing {self.eluting_solvent}.'
                ),

                SanityCheck(
                    condition=(
                        self.eluting_volume * self.eluting_repeats
                        <= to_vessel_max_volume
                    ),
                    error_msg=f'Eluting volume ({self.eluting_volume * self.eluting_repeats} mL) is\
 > to_vessel max volume ({to_vessel_max_volume} mL).'
                ),
            ])

            # Moving to and from the same vessel
            if self.from_vessel == self.to_vessel:
                # Get the max volume of the buffer flask
                buffer_flask_max_volume = graph.nodes[
                    self.buffer_flask
                ]['max_volume']

                # Add new check to list
                checks.append(
                    SanityCheck(
                        condition=(self.eluting_volume * self.eluting_repeats
                                   <= buffer_flask_max_volume),
                        error_msg=f'Eluting volume ({self.eluting_volume * self.eluting_repeats} mL) is\
 > buffer flask max volume ({buffer_flask_max_volume} mL).'
                    )
                )

        return checks

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        # Not going from and to same vessel.
        if self.from_vessel != self.to_vessel:

            # No elution
            if not self.eluting_solvent:
                return self.get_no_elution_steps()

            # With elution
            else:

                # Internal props not added
                if self.from_vessel_max_volume is None:
                    return []

                # Eluting volume <= from_vessel max volume, one transfer
                elif self.eluting_volume <= self.from_vessel_max_volume:
                    return self.get_non_portionwise_elution_steps()

                # Eluting volume > from_vessel max volume, portionwise transfers
                else:
                    return self.get_portionwise_elution_steps()

        # Going from and to same vessel.
        else:

            # No elution
            if not self.eluting_solvent:
                return self.get_no_elution_steps_with_buffer()

            # With elution
            else:

                if self.from_vessel_max_volume is None:
                    return []

                # Eluting volume <= from_vessel max volume, one transfer
                elif self.eluting_volume <= self.from_vessel_max_volume:
                    return self.get_non_portionwise_elution_steps_with_buffer()

                # Eluting volume > from_vessel max volume, portionwise transfer
                else:
                    # If from_vessel max volume > eluting volume and from vessel
                    # and to vessel are the same then eluting will overflow
                    # the flask. Raise error in final sanity check.
                    return []

    def get_no_elution_steps(self) -> List[Step]:
        """Single transfer, no elution, with no buffer flask

        Returns:
            List[Step]: List of transfer steps
        """

        return (
            self.get_filter_through_transfer_steps()
            + self.get_flush_cartridge_steps()
        )

    def get_non_portionwise_elution_steps(self) -> List[Step]:
        """Single transfer, silgle elution, no buffer flask.

        Returns:
            List[Step]: List of transfer steps
        """

        return (
            self.get_filter_through_transfer_steps()
            + self.get_single_elution_steps()
            + self.get_flush_cartridge_steps()
        )

    def get_portionwise_elution_steps(self) -> List[Step]:
        """Single transfer, portionwise elution, no buffer flasks.

        Returns:
            List[Step]: List of transfer steps
        """

        return (
            self.get_filter_through_transfer_steps()
            + self.get_multi_elution_steps()
            + self.get_flush_cartridge_steps()
        )

    def get_no_elution_steps_with_buffer(self) -> List[Step]:
        """Single transfer, no elution, using buffer flasks

        Returns:
            List[Step]: List of transfer steps
        """

        return (
            self.get_filter_through_transfer_to_buffer_steps()
            + self.get_flush_cartridge_to_buffer_steps()
            + self.get_transfer_back_from_buffer_steps()
        )

    def get_non_portionwise_elution_steps_with_buffer(self) -> List[Step]:
        """Single transfer, single elution, using buffer flask

        Returns:
            List[Step]: List of transfer steps
        """

        return (
            self.get_filter_through_transfer_to_buffer_steps()
            + self.get_flush_cartridge_to_buffer_steps()
            + self.get_single_elution_to_buffer_steps()
            + self.get_clean_from_and_to_vessel_steps()
            + self.get_transfer_back_from_buffer_steps()
        )

    ###########
    # General #
    ###########

    def get_filter_through_transfer_steps(self) -> List[Step]:
        """Get the Transfer step(s) for filtering through a cartridge

        Returns:
            List[Step]: List of Transfer steps
        """

        return [
            Transfer(
                from_vessel=self.from_vessel,
                to_vessel=self.to_vessel,
                through=self.through,
                volume=self.from_vessel_max_volume,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed
            )
        ]

    def get_flush_cartridge_steps(self) -> Optional[List[Step]]:
        """Get the transfer steps if flushing the cartridge vessel

        Returns:
            Optional[List[Step]]: List of transfer steps if flushing, else []
        """

        return [
            Transfer(
                from_vessel=self.flush_cartridge_vessel,
                to_vessel=self.to_vessel,
                through=self.through,
                volume=self.cartridge_dead_volume,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed
            )
        ] if self.flush_cartridge_vessel else []

    ###########
    # Elution #
    ###########

    def get_single_elution_steps(self) -> List[Step]:
        """Get the transfer steps for a single elution.

        Returns:
            List[Step]: Transfer steps for single elution
        """

        eluting_steps = [
            Transfer(
                from_vessel=self.eluting_solvent_vessel,
                to_vessel=self.from_vessel,
                volume=self.eluting_volume
            ),

            Transfer(
                from_vessel=self.from_vessel,
                to_vessel=self.to_vessel,
                through=self.through,
                volume=self.eluting_volume,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed
            )
        ]

        # More than one elution needed, add Repeat step on above steps
        if self.eluting_repeats > 1:
            return [
                Repeat(repeats=self.eluting_repeats, children=eluting_steps)
            ]

        return eluting_steps

    def get_multi_elution_steps(self) -> List[Step]:
        """Get the steps for doing multiple elutions at once

        Returns:
            List[Step]: Multiple elution steps
        """

        # Number of elution portions
        n_portions = math.floor(
            self.eluting_volume / self.from_vessel_max_volume
        )

        # Final portion volume
        final_portion_vol = self.eluting_volume % self.from_vessel_max_volume

        # Get volume per portion required
        portion_vol = (self.eluting_volume - final_portion_vol) / n_portions

        # Repeat elution multiple times
        eluting_steps = [
            Repeat(
                repeats=n_portions,
                children=self.get_single_portion_elution_steps(portion_vol)
            ),
        ] + self.get_single_portion_elution_steps(final_portion_vol)

        # More than one repeat needed, repeat again
        if self.eluting_repeats > 1:
            return [
                Repeat(repeats=self.eluting_repeats, children=eluting_steps)
            ]

        return eluting_steps

    def get_single_portion_elution_steps(
        self, volume: float
    ) -> Optional[List[Step]]:
        """Get the steps needed for eluting a single portion

        Args:
            volume (float): Volume to transfer

        Returns:
            Optional[List[Step]]: Elution steps if volume defined, else []
        """

        return [
            Transfer(
                from_vessel=self.eluting_solvent_vessel,
                to_vessel=self.from_vessel,
                volume=volume
            ),

            Transfer(
                from_vessel=self.from_vessel,
                to_vessel=self.to_vessel,
                through=self.through,
                volume=volume,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed
            )
        ] if volume else []

    #######################
    # General With Buffer #
    #######################

    def get_filter_through_transfer_to_buffer_steps(self) -> List[Step]:
        """Get the Transfer step for going to a buffer flask via a through node

        Returns:
            List[Step]: Transfer steps
        """

        return [
            Transfer(
                from_vessel=self.from_vessel,
                to_vessel=self.buffer_flask,
                through=self.through,
                volume=self.from_vessel_max_volume,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed
            )
        ]

    def get_flush_cartridge_to_buffer_steps(self) -> Optional[List[Step]]:
        """Get the Transfer steps for flushing through a cartridge to the
        buffer flask

        Returns:
            Optional[List[Step]]: Transfer steps if a flush cartridge vessel is
                                defined, else []
        """

        return [
            Transfer(
                from_vessel=self.flush_cartridge_vessel,
                to_vessel=self.buffer_flask,
                through=self.through,
                volume=self.cartridge_dead_volume,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed
            )
        ] if self.flush_cartridge_vessel else []

    def get_transfer_back_from_buffer_steps(self) -> List[Step]:
        """Get Transfer steps from buffer flask back to vessel

        Returns:
            List[Step]: Transfer steps
        """

        return [
            Transfer(
                from_vessel=self.buffer_flask,
                to_vessel=self.to_vessel,
                volume=self.from_vessel_max_volume,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed
            )
        ]

    #######################
    # Elution With Buffer #
    #######################

    def get_clean_from_and_to_vessel_steps(self) -> List[Step]:
        """Get the clean vessel steps for the from_vessel

        Returns:
            List[Step]: CleanVessel steps
        """

        return [
            CleanVessel(
                vessel=self.from_vessel,
                solvent=self.eluting_solvent
            )
        ]

    def get_single_elution_to_buffer_steps(self) -> List[Step]:
        """Get the steps for a single elution to the buffer flask./

        Returns:
            List[Step]: Elution steps
        """

        eluting_steps = [
            Transfer(
                from_vessel=self.eluting_solvent_vessel,
                to_vessel=self.from_vessel,
                volume=self.eluting_volume
            ),

            Transfer(
                from_vessel=self.from_vessel,
                to_vessel=self.buffer_flask,
                through=self.through,
                volume=self.eluting_volume,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed
            )
        ]

        # More than one repeat required, Repeat steps above X times
        if self.eluting_repeats > 1:
            return [
                Repeat(repeats=self.eluting_repeats, children=eluting_steps)
            ]

        return eluting_steps

    @property
    def buffer_flasks_required(self) -> int:
        """Get the total number of buffer flasks required.

        Returns:
            int: Number of buffer flasks required
        """

        return 1 if self.to_vessel == self.from_vessel else 0
