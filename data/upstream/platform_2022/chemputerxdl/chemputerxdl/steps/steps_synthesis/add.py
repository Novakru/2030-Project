"""
.. module:: steps_synthesis.add
    :platforms; Unix, Windows
    :synopsis: XDL Step for adding a material to a vessel

"""

from chemputerxdl.steps.steps_utility.cleaning import CleanBackbone
from typing import Optional, List, Dict, Any
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import Step
from xdl.steps.templates import AbstractAddStep
from xdl.constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from xdl.utils.misc import SanityCheck
from xdl.utils.prop_limits import (
    VOLUME_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    TIME_PROP_LIMIT,
    POSITIVE_INT_PROP_LIMIT,
    ADD_PURPOSE_PROP_LIMIT
)

# Relative
from ..steps_utility import (
    PrimePumpForAdd, Wait, StopStir, StartStir, FlushTubing)
from ..steps_base import CMove
from ..base_step import ChemputerStep
from ...constants import (
    DEFAULT_AFTER_ADD_WAIT_TIME,
    DEFAULT_VISCOUS_ASPIRATION_SPEED,
)
from ...utils.execution import (
    get_waste_vessel,
    get_reagent_vessel,
    get_cartridge,
    get_vessel_type,
)
from ...utils.prop_limits import PORT_PROP_LIMIT
from ...constants import PORT_PROP_TYPE

class Add(ChemputerStep, AbstractAddStep):
    """Add given volume of given reagent to given vessel.

    Args:
        reagent (str): Reagent to add.
        volume (float): Volume of reagent to add.
        vessel (str): Vessel name to add reagent to.
        port (str): vessel port to use.
        through (str): Substrate to pass reagent through on way to vessel
        move_speed (float): Speed in mL / min to move liquid at. (optional)
        aspiration_speed (float): Aspiration speed (speed at which liquid is
            pulled out of reagent_vessel).
        dispense_speed (float): Dispense speed (speed at which liquid is pushed
            from pump into vessel).
        time (float): Time to spend dispensing liquid. Works by changing
            dispense_speed. Note: The time given here will not be the total step
            execution time, it will be the total time spent dispensing from the
            pump into self.vessel during the addition.
        stir (bool): If True, stirring will be started before addition.
        stir_speed (float): RPM to stir at, only relevant if stir = True.
        through_cartridge (str): Internal property. Node name of cartridge to
            pass reagent through on way to vessel.
        confirm_solid (bool): If False, skip Confirm step for solid addition
        priming_volume (float): Volume of reagent to use for priming tubing.
        cleaning (bool): If true, the first step will be CleanBackbone, with the
            solvent specified in cleaning_solvent. Default is False.
        cleaning_solvent (str): Solvent to clean backbone with. Must be given
            if cleaning is True. Defaults to None.
        cleaning_repeats (int): Number of repeats for cleaning the backbone if
            cleaning is True. Defaults to one.

        anticlogging (bool): If True, a technique will be used to avoid clogging
            where reagent is added in small portions, each one followed by a
            small portion of solvent.
        anticlogging_solvent (str): Solvent to add between reagent additions
            during anticlogging routine.
        anticlogging_solvent_volume (float): Optional. Portion of solvent to add
            in each cycle of anticlogging add routine.
        anticlogging_reagent_volume (float): Optional. Portion of reagent to add
            in each cycle of anticlogging add routine.
        anticlogging_solvent_vessel (str): Given internally. Vessel containing
            anticlogging solvent.

        reagent_vessel (str): Given internally. Vessel containing reagent.
        waste_vessel (str): Given internally. Vessel to send waste to.
    """

    DEFAULT_DROPWISE_DISPENSE_SPEED = 0.1

    DEFAULT_PROPS = {
        # Mandatory
        'stir': False,
        'dropwise': False,
        'viscous': False,
        'time': None,
        'stir_speed': '250 RPM',
        'purpose': None,
        'speed': 40,  # move speed

        'port': None,
        'through': None,
        'anticlogging_solvent': None,
        'move_speed': 40,  # mL / min
        'aspiration_speed': 40,  # mL / min
        'dispense_speed': 40,  # mL / min
        'anticlogging': False,
        'anticlogging_solvent_volume': '2 mL',
        'anticlogging_reagent_volume': '10 mL',
        'prime_n_times': 1,
        'priming_volume': '3 mL',
        'cleaning': False,
        'cleaning_solvent': None,
        'cleaning_repeats': 1,
    }

    PROP_TYPES = {
        # Mandatory
        'vessel': VESSEL_PROP_TYPE,
        'reagent': REAGENT_PROP_TYPE,
        'volume': float,
        'viscous': bool,
        'dropwise': bool,
        'time': float,
        'stir': bool,
        'stir_speed': float,
        'purpose': str,

        'speed': float,
        'port': PORT_PROP_TYPE,
        'through': str,
        'move_speed': float,
        'aspiration_speed': float,
        'dispense_speed': float,
        'anticlogging': bool,
        'anticlogging_solvent': REAGENT_PROP_TYPE,
        'anticlogging_solvent_volume': float,
        'anticlogging_reagent_volume': float,
        'through_cartridge': str,
        'reagent_vessel': str,
        'waste_vessel': str,
        'vessel_type': str,
        'anticlogging_solvent_vessel': str,
        'prime_n_times': int,
        'priming_volume': float,
        'cleaning': bool,
        'cleaning_solvent': str,
        'cleaning_repeats': int,
    }

    INTERNAL_PROPS = [
        'through_cartridge',
        'reagent_vessel',
        'waste_vessel',
        'vessel_type',
        'anticlogging_solvent_vessel',
    ]

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'port': PORT_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'purpose': ADD_PURPOSE_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'anticlogging_solvent_volume': VOLUME_PROP_LIMIT,
        'anticlogging_reagent_volume': VOLUME_PROP_LIMIT,
        'prime_n_times': POSITIVE_INT_PROP_LIMIT,
        'priming_volume': VOLUME_PROP_LIMIT,
    }

    def __init__(
        self,
        reagent: str,
        vessel: str,
        volume: float,
        speed: Optional[float] = 'default',
        port: Optional[str] = 'default',
        through: Optional[str] = 'default',
        dropwise: bool = 'default',
        purpose: str = None,
        move_speed: Optional[float] = 'default',
        aspiration_speed: Optional[float] = 'default',
        dispense_speed: Optional[float] = 'default',
        viscous: Optional[bool] = 'default',
        time: Optional[float] = 'default',
        stir: Optional[bool] = 'default',
        stir_speed: Optional[float] = 'default',
        confirm_solid: Optional[bool] = 'default',
        prime_n_times: Optional[int] = 'default',
        priming_volume: Optional[float] = 'default',

        anticlogging: Optional[bool] = 'default',
        anticlogging_solvent: Optional[str] = 'default',
        anticlogging_solvent_volume: Optional[float] = 'default',
        anticlogging_reagent_volume: Optional[float] = 'default',
        cleaning: Optional[float] = 'default',
        cleaning_solvent: Optional[float] = 'default',
        cleaning_repeats: Optional[int] = 'default',

        # Internal properties
        through_cartridge: Optional[str] = None,
        reagent_vessel: Optional[str] = None,
        waste_vessel: Optional[str] = None,
        vessel_type: Optional[str] = None,
        anticlogging_solvent_vessel: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Obtain the reagent vessel if not defined
        if not self.reagent_vessel:
            self.reagent_vessel = get_reagent_vessel(graph, self.reagent)

        # Use the closest waste vessel to the reagent
        self.waste_vessel = get_waste_vessel(
            graph, self.reagent_vessel
        )

        # Obtain the anticlogging vessel if a solvent has been supplied
        if self.anticlogging_solvent and not self.anticlogging_solvent_vessel:
            self.anticlogging_solvent_vessel = get_reagent_vessel(
                graph, self.anticlogging_solvent
            )

        # Obtain the through cartridge if through nodes have been defined
        if not self.through_cartridge and self.through:
            self.through_cartridge = get_cartridge(graph, self.through)

        # Obtian the vessel type if not defined
        if not self.vessel_type:
            self.vessel_type = get_vessel_type(graph, self.vessel)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        # List to hold the execution steps
        steps = []

        # Get the anticlogging steps
        if self.anticlogging:
            steps = self.get_anticlogging_add_steps()

        # No anticlogging needed, get the Add steps
        else:
            steps = self.get_add_steps()

        # Begin with CleanBackbone if cleaning == True
        if self.cleaning:
            steps.insert(0, CleanBackbone(
                solvent=self.cleaning_solvent,
                repeats=self.cleaning_repeats,
            ))

        # Add a step to flush the tubung
        steps.append(
            FlushTubing(
                to_vessel=self.vessel,
                to_port=self.port,
                dispense_speed=self.get_dispense_speed(),
                through_cartridge=self.through_cartridge,
            )
        )

        # Add Stirring step if stirring required
        if self.stir:
            steps.insert(
                0,
                StartStir(
                    vessel=self.vessel,
                    vessel_type=self.vessel_type,
                    stir_speed=self.stir_speed
                )
            )

        # Stirring not required, add a stop stirring step
        else:
            steps.insert(0, StopStir(vessel=self.vessel))

        # do nothing if the volume is zero
        if self.volume == 0:
            return []

        return steps

    def get_add_steps(self) -> List[Step]:
        """Get all Addition steps.

        Returns:
            List[Step]: Steps associated with addition
        """

        # Set pump aspiration speed depending on viscosity
        aspiration_speed = (
            self.aspiration_speed if not self.viscous
            else DEFAULT_VISCOUS_ASPIRATION_SPEED
        )

        # Return addition steps
        return [
            PrimePumpForAdd(
                reagent=self.reagent,
                volume=self.priming_volume,
                waste_vessel=self.waste_vessel,
                prime_n_times=self.prime_n_times,
                move_speed=self.move_speed,
                aspiration_speed=aspiration_speed,
            ),
            CMove(
                from_vessel=self.reagent_vessel,
                to_vessel=self.vessel,
                to_port=self.port,
                volume=self.volume,
                through=self.through_cartridge,
                move_speed=self.move_speed,
                aspiration_speed=aspiration_speed,
                dispense_speed=self.get_dispense_speed()
            ),
            Wait(time=DEFAULT_AFTER_ADD_WAIT_TIME)
        ]

    def get_anticlogging_add_steps(self) -> List[Step]:
        """Get all addition steps associated with anticlogging.

        Returns:
            List[Step]: Steps associated with anticlogging addition
        """

        # Obtain the dispense speed for the pumps
        dispense_speed = self.get_dispense_speed()

        # Add step for priming the pump
        steps = [
            PrimePumpForAdd(
                reagent=self.reagent,
                volume=self.priming_volume,
                waste_vessel=self.waste_vessel,
                prime_n_times=self.prime_n_times,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed,
            )
        ]

        # Calculate the total number of additions required
        n_adds = int(self.volume / self.anticlogging_reagent_volume) + 1

        # Add a Movement step for each addition required
        for _ in range(n_adds):
            steps.extend([
                CMove(
                    from_vessel=self.reagent_vessel,
                    to_vessel=self.vessel,
                    to_port=self.port,
                    volume=self.anticlogging_reagent_volume,
                    move_speed=self.move_speed,
                    aspiration_speed=self.aspiration_speed,
                    dispense_speed=dispense_speed),
                CMove(
                    from_vessel=self.anticlogging_solvent_vessel,
                    to_vessel=self.vessel,
                    to_port=self.port,
                    volume=self.anticlogging_solvent_volume,
                    move_speed=self.move_speed,
                    aspiration_speed=self.aspiration_speed,
                    dispense_speed=dispense_speed),
            ])

        # Add in a wait time after addition
        steps.append(Wait(time=DEFAULT_AFTER_ADD_WAIT_TIME))

        return steps

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Get any requirements this step needs

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary contianing step requirements
        """

        return {
            'vessel': {
                'stir': self.stir,
            }
        }

    def get_dispense_speed(self) -> float:
        """Get the current dispensing speed

        Returns:
            float: Dispensing speed
        """
        # Need this so SynthReader doesn't crash when using zero volumes
        if self.volume == 0:
            return Add.DEFAULT_PROPS['dispense_speed']

        # Time has been supplied, calculate dispensing speed
        elif self.time:
            return self.volume / (self.time / 60)

        elif self.dropwise:
            return Add.DEFAULT_DROPWISE_DISPENSE_SPEED

        # Return already defined speed
        return self.dispense_speed

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=not self.through or self.through_cartridge,
                error_msg=f'Trying to add through "{self.through}" but cannot\
 find cartridge containing {self.through}.'
            ),

            SanityCheck(
                condition=self.reagent_vessel,
                error_msg=f'No reagent flask present containing\
 "{self.reagent}".'
            ),

            SanityCheck(
                condition=self.vessel,
                error_msg=f'{self.vessel} cannot be None.'
            ),

            SanityCheck(
                condition=self.volume is not None,
                error_msg='Volume must be given.'
            )
        ]

    def scale(self, scale: float):
        """Scale volumes by a given factor

        Args:
            scale (float): Scaling factor
        """

        if self.volume is not None:
            self.volume *= scale
