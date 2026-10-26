"""
.. module:: steps_synthesis.clean_vessel
    :platforms: Unix, Windows
    :synopsis: XDL Step for cleaning a vessel

"""

from typing import Optional, List
from networkx import MultiDiGraph

# XDL
from xdl.steps import Step
from xdl.steps.templates import AbstractCleanVesselStep
from xdl.constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from xdl.utils.misc import SanityCheck
from xdl.utils.prop_limits import (
    TIME_PROP_LIMIT,
    TEMP_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    VOLUME_PROP_LIMIT,
)
from xdl.utils.graph import undirected_neighbors

# Relative
from .dry import Dry
from ..base_step import ChemputerStep
from ..steps_utility import (
    StartStir,
    StopStir,
    Wait,
    HeatChillToTemp,
    HeatChillReturnToRT,
    Unlock
)
from ..steps_base import CMove, CRotavapLiftDown, CRotavapLiftUp
from ...utils.execution import (
    get_vacuum_configuration,
    get_nearest_node,
    get_reagent_vessel,
    get_heater_chiller,
    get_vessel_type,
)
from ...constants import (
    CHEMPUTER_WASTE,
    STIRRER_CLASSES,
    ROTAVAP_CLASSES,
    HEATER_CLASSES
)
from ...utils.prop_limits import VESSEL_TYPE_PROP_LIMIT

class CleanVessel(ChemputerStep, AbstractCleanVesselStep):
    """Clean given vessel with given solvent.

    With regards to dry params, the logic is as follows:

        ``dry=None`` -> Dry if possible, don't throw error if not,
            unless ``dry_time`` and ``dry_temp`` passed then throw error.
        ``dry=True`` -> Dry if possible, throw error if not.
        ``dry=False`` -> Do not dry even if possible,
            throw error if ``dry_time`` and ``dry_temp`` passed.

    Args:
        vessel (str): Vessel to clean.
        solvent (str): Solvent to clean vessel with.
        stir_time (float): Time to stir for after solvent is added.
        stir_speed (float): Speed to stir at in RPM.
        volume (float): Volume of solvent to use. If not supplied will be
            given internally according to vessel max volume.
        repeats (int): Number of repeats to do.
        solvent_vessel (str): Given internally. Flask containing solvent.
        waste_vessel (str): Given internally. Vessel to send waste solvent
            to.
        vacuum (str): Internal property. Used to tell if drying is possible.
    """

    DEFAULT_PROPS = {
        'temp': None,
        'volume': None,
        'stir_time': '1 minute',
        'repeats': 2,
        'dry': None,
        'dry_time': None,
        'dry_temp': None,
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'solvent': REAGENT_PROP_TYPE,
        'stir_time': float,
        'stir_speed': float,
        'temp': float,
        'dry': bool,
        'dry_time': float,
        'dry_temp': float,
        'volume': float,
        'repeats': int,
        'can_dry': bool,
        'solvent_vessel': str,
        'waste_vessel': str,
        'vessel_type': str,
        'heater': str,
        'chiller': str,
        'has_stirrer': bool,
    }

    INTERNAL_PROPS = [
        'solvent_vessel',
        'waste_vessel',
        'vessel_type',
        'heater',
        'chiller',
        'can_dry',
        'has_stirrer',
        'stir_speed',
    ]

    PROP_LIMITS = {
        'stir_time': TIME_PROP_LIMIT,
        'dry_time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'temp': TEMP_PROP_LIMIT,
        'dry_temp': TEMP_PROP_LIMIT,
        'volume': VOLUME_PROP_LIMIT,
        'vessel_type': VESSEL_TYPE_PROP_LIMIT,
    }

    DO_NOT_SCALE = True

    #: Fraction of vessel max volume to use as solvent volume in CleanVessel
    # step.
    CLEAN_VESSEL_VOLUME_FRACTION: float = 0.5

    #: Volume in mL of liquid to transfer to waste before start of cleaning to
    # ensure that all residual liquid is gone, and also at end to ensure that
    # all solvent is gone.
    EXCESS_WITHDRAWAL_VOLUME: float = 7.5

    #: Time to dry for in seconds if user doesn't supply `dry_time` prop. Reason
    #: this doesn't use normal default prop system is that the default should be
    #: `None`, so that it's known if user passed a value or not.
    FALLBACK_DRY_TIME: float = 3600

    #: Temp to dry at if user doesn't supply `dry_temp` prop. Reason
    #: this doesn't use normal default prop system is that the default should be
    #: `None`, so that it's known if user passed a value or not.
    FALLBACK_DRY_TEMP: float = 25

    #: Speed to stir at in rotavap in RPM
    ROTAVAP_STIR_SPEED: int = 150

    #: Speed to stir at with hotplate in RPM
    HOTPLATE_STIR_SPEED: int = 250

    #: Speed to stir at with stirrer in RPM
    STIRRER_STIR_SPEED: int = 500

    def __init__(
        self,
        vessel: str,
        solvent: str,
        stir_time: Optional[float] = 'default',
        temp: Optional[float] = 'default',
        dry: Optional[bool] = 'default',
        dry_time: Optional[float] = 'default',
        dry_temp: Optional[float] = 'default',
        volume: Optional[float] = 'default',
        repeats: Optional[int] = 'default',

        # Internal properties
        solvent_vessel: Optional[str] = None,
        waste_vessel: Optional[str] = None,
        can_dry: Optional[str] = None,
        vessel_type: Optional[str] = None,
        heater: Optional[str] = None,
        chiller: Optional[str] = None,
        has_stirrer: Optional[bool] = False,
        stir_speed: Optional[float] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/repeats up appropriate items in preparation for execution.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Obtain volume is not defined
        if self.volume is None:
            self.volume = (
                graph.nodes[self.vessel]['max_volume']
                * self.CLEAN_VESSEL_VOLUME_FRACTION
            )

        # Obtain vessel type if not defined
        if not self.vessel_type:
            self.vessel_type = get_vessel_type(graph, self.vessel)

        # Obtain the heater and chiller attached to current vessel
        self.heater, self.chiller = get_heater_chiller(graph, self.vessel)

        # Obtain waste vessel if not defined
        if not self.waste_vessel:
            self.waste_vessel = get_nearest_node(
                graph, self.vessel, CHEMPUTER_WASTE)

        # Obtain solvent vessel if not defined
        if not self.solvent_vessel:
            self.solvent_vessel = get_reagent_vessel(graph, self.solvent)

        # Obtain vacuum configuration
        vacuum_info = get_vacuum_configuration(graph, self.vessel)

        self.can_dry = (
            vacuum_info['source'] is not None
            or self.vessel_type == 'rotavap'
        )

        # Iterate through all nodes in the graph
        for node in graph.nodes():
            # Found a ChemputerFlask
            if graph.nodes[node]['class'] == 'ChemputerFlask':
                # Node's chemical matches out solvent, set solvent vessel
                if graph.nodes[node]['chemical'] == self.solvent:
                    self.solvent_vessel = node
                    break

        # Check for attached heaters
        self.check_for_heater()

        # Check whether the vessel itself can stir
        if graph.nodes[self.vessel]['class'] in ROTAVAP_CLASSES:
            if self.stir_speed is None:
                self.stir_speed = CleanVessel.ROTAVAP_STIR_SPEED
            self.has_stirrer = True
        # Check whether a stirrer is attached to the vessel
        else:
            for _, data in undirected_neighbors(graph, self.vessel, data=True):
                if data['class'] in STIRRER_CLASSES:
                    if self.stir_speed is None:
                        self.stir_speed = CleanVessel.STIRRER_STIR_SPEED
                    self.has_stirrer = True
                elif data['class'] in HEATER_CLASSES:
                    if self.stir_speed is None:
                        self.stir_speed = CleanVessel.HOTPLATE_STIR_SPEED
                    self.has_stirrer = True

    def check_for_heater(self):
        """Checks if a heater is present
        """

        # Set temp to None if temp is defined but no heater/chiller set
        if (
                self.temp is not None and not (
                    self.heater or self.chiller or self.vessel_type == 'rotavap'
                )
        ):
            self.temp = None

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """
        return [
            SanityCheck(
                condition=self.solvent_vessel,
                error_msg=f'No solvent vessel found in graph for {self.solvent}'
            ),

            SanityCheck(
                condition=self.waste_vessel,
                error_msg=f'No waste vessel found for "{self.vessel}".'
            ),

            SanityCheck(
                condition=self.repeats > 0,
                error_msg=f'`repeats` property must be > 0. {self.repeats} is an\
 invalid value.'
            ),

            SanityCheck(
                condition=self.volume and self.volume > 0,
                error_msg=f'`volume` must be > 0. {self.volume} is an invalid\
 value.'
            ),

            SanityCheck(
                condition=(
                    (not self.dry_time and not self.dry_temp)
                    or self.dry is not False
                ),
                error_msg='Dry parameters given but `dry` is `False`.'
            ),

            SanityCheck(
                condition=(
                    (not self.dry_time and not self.dry_temp)
                    or self.can_dry is not False
                ),
                error_msg=f'Dry parameters given but drying is not possible in\
 {self.vessel}.'
            ),

            SanityCheck(
                condition=(
                    self.dry is not True or self.can_dry
                ),
                error_msg=f'Trying to dry but drying is not possible in\
 {self.vessel}.'
            )
        ]

    def get_steps(self) -> List[Step]:
        """Get the list of steps to execute

        Returns:
            List[Step]: Steps to execute
        """

        # Move any residual liquid left in the flask to waste.
        steps = [
            CMove(
                from_vessel=self.vessel,
                to_vessel=self.waste_vessel,
                volume=CleanVessel.EXCESS_WITHDRAWAL_VOLUME
            )
        ]

        # Iterate through total number of repeats to perform
        for i in range(self.repeats):
            volume_to_withdraw = self.volume

            # On last withdrawal, withdraw excess to ensure no solvent is left
            # in vessel. ``None`` check is required so that you are not doing
            # ``None + float`` before compilation and getting an error.
            if volume_to_withdraw is not None and i + 1 == self.repeats:
                volume_to_withdraw = (
                    self.volume + CleanVessel.EXCESS_WITHDRAWAL_VOLUME)

            steps.extend(

                # Start stirring
                self.get_start_stir_steps()

                # Add solvent, stir, and move the solvent to waste.
                + [
                    CMove(
                        from_vessel=self.solvent_vessel,
                        to_vessel=self.vessel,
                        volume=self.volume
                    ),
                    Wait(time=self.stir_time),
                    CMove(
                        from_vessel=self.vessel,
                        to_vessel=self.waste_vessel,
                        volume=volume_to_withdraw
                    ),
                ]

                # Stop stirring
                + self.get_stop_stir_steps()
            )

        # Dry is `self.dry` is `True`, or `self.dry` is `None` and drying is
        # possible.
        if self.dry or (self.dry is None and self.can_dry):

            # Establish dry time and temp to use
            dry_temp = self.dry_temp or CleanVessel.FALLBACK_DRY_TEMP
            dry_time = self.dry_time or CleanVessel.FALLBACK_DRY_TIME

            # Create Dry step
            steps.append(Dry(vessel=self.vessel,
                             temp=dry_temp,
                             time=dry_time))

        # Temperature is defined, add steps to ramp up/down temp
        if self.temp is not None and (self.temp < 20 or self.temp > 25):
            steps.insert(
                1, HeatChillToTemp(vessel=self.vessel, temp=self.temp)
            )

            steps.append(HeatChillReturnToRT(vessel=self.vessel, stir=False))

        # Bracket the steps with liftup/down if it's a rotavap
        if self.vessel_type == 'rotavap':
            steps.insert(0, CRotavapLiftDown('rotavap'))
            steps.append(CRotavapLiftUp('rotavap'))

        # Appending unlock because vessel can now be reused
        steps.append(Unlock(nodes=[self.vessel]))

        # Return all steps
        return steps

    def get_start_stir_steps(self) -> List[Optional[Step]]:
        """Get steps associated with starting stirring

        Returns:
            List[Optional[Step]]: Steps for StartStir
        """

        # Stirrer is defined, add StartStir
        if self.has_stirrer:
            return [StartStir(vessel=self.vessel,
                              stir_speed=self.stir_speed)]

        # Default to no steps
        return []

    def get_stop_stir_steps(self) -> List[Optional[Step]]:
        """Get steps associated with stopping stirring.

        Returns:
            List[Optional[Step]]: Steps for StopStir
        """

        # Stirrer is defined, add StopStir
        if self.has_stirrer:
            return [StopStir(vessel=self.vessel)]

        # Default to no steps
        return []
