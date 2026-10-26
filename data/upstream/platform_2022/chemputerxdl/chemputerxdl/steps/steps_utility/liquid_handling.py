"""
.. module:: steps_utility.liquid_handling
    :platforms: Unix, Windows
    :synopsis: XDL steps to perform liquid handling operations

"""

from typing import Optional, List
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import AbstractStep, Step
from xdl.steps.templates import AbstractTransferStep
from xdl.steps.special_steps import Repeat, Wait
from xdl.utils.prop_limits import (
    VOLUME_PROP_LIMIT,
    TIME_PROP_LIMIT,
    POSITIVE_INT_PROP_LIMIT,
)
from xdl.utils.misc import SanityCheck
from xdl.constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE

# Relative
from .heatchill import StopHeatChill
from .stirring import StartStir, StopStir
from ..base_step import ChemputerStep
from ..steps_base import CMove
from ...constants import (
    DEFAULT_PORTS,
    DEFAULT_VISCOUS_ASPIRATION_SPEED,
    DEFAULT_AIR_FLUSH_TUBE_VOLUME,
)
from ...utils.execution import (
    get_reagent_vessel,
    get_cartridge,
    get_vessel_stirrer,
    node_in_graph,
    get_heater_chiller,
    get_flush_tube_vessel,
    get_waste_vessel,
)
from ...utils.prop_limits import PORT_PROP_LIMIT
from ...constants import PORT_PROP_TYPE

class PrimePumpForAdd(ChemputerStep, AbstractStep):
    """Prime pump attached to given reagent flask in anticipation of Add step.

    Args:
        reagent (str): Reagent to prime pump for addition.
        volume (float): Volume to prime
        reagent_vessel (str): Reagent vessel to use
        waste_vessel (str): Waste vessel to use
    """

    DEFAULT_PROPS = {
        'volume': '3 mL',
        'prime_n_times': 1,
        'move_speed': 40,  # mL / min
        'aspiration_speed': 40,  # mL / min
        'dispense_speed': 40,  # mL / min
    }

    INTERNAL_PROPS = [
        'reagent_vessel',
        'waste_vessel',
    ]

    PROP_TYPES = {
        'reagent': REAGENT_PROP_TYPE,
        'volume': float,
        'reagent_vessel': str,
        'waste_vessel': str,
        'prime_n_times': int,
        'move_speed': float,
        'aspiration_speed': float,
        'dispense_speed': float,
    }

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'prime_n_times': POSITIVE_INT_PROP_LIMIT,
    }

    def __init__(
        self,
        reagent: str,
        volume: Optional[float] = 'default',
        prime_n_times: Optional[int] = 'default',
        move_speed: Optional[float] = 'default',
        aspiration_speed: Optional[float] = 'default',
        dispense_speed: Optional[float] = 'default',

        # Internal properties
        reagent_vessel: Optional[str] = None,
        waste_vessel: Optional[str] = None,
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

        if not self.waste_vessel:
            self.waste_vessel = get_waste_vessel(graph, self.reagent_vessel)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        return [Repeat(
            repeats=self.prime_n_times,
            children=[
                CMove(
                    from_vessel=self.reagent_vessel,
                    to_vessel=self.waste_vessel,
                    volume=self.volume,
                    move_speed=self.move_speed,
                    aspiration_speed=self.aspiration_speed,
                    dispense_speed=self.dispense_speed
                ),
                FlushTubing(to_vessel=self.waste_vessel)
            ])
        ]

class FlushTubing(ChemputerStep, AbstractStep):
    """Flush tubing with inert gas (if present), otherwise air (if present),
    otherwise do nothing.

    Args:
        to_vessel (str): Vessel to move to
        to_port (str, optional): Port to move to. Defaults to None.
        volume (float, optional): Volume to flush. Defaults to 'default'.
        dispense_speed (float, optional): Pump speed. Defaults to 'default'.
        through_cartridge (str, optional): Cartridge to move through.
                                            Defaults to 'None'.
        flush_tube_vessel (str, optional): Vessel to move flushed solvent to.
                                            Defaults to 'None'.
    """

    PROP_TYPES = {
        'to_vessel': VESSEL_PROP_TYPE,
        'to_port': PORT_PROP_TYPE,
        'volume': float,
        'dispense_speed': float,
        'through_cartridge': str,
        'flush_tube_vessel': str,
    }

    DEFAULT_PROPS = {
        'dispense_speed': 40,
        'volume': f'{DEFAULT_AIR_FLUSH_TUBE_VOLUME} mL',
        'to_port': None,
        'through_cartridge': None,
    }

    INTERNAL_PROPS = [
        'flush_tube_vessel',
    ]

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
    }

    def __init__(
        self,
        to_vessel: str,
        to_port: Optional[str] = 'default',
        volume: Optional[float] = 'default',
        dispense_speed: Optional[float] = 'default',
        through_cartridge: Optional[str] = 'default',

        # Internal props
        flush_tube_vessel: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Obtain the flush tube vessel if not defined
        if not self.flush_tube_vessel:
            self.flush_tube_vessel = get_flush_tube_vessel(
                graph, self.to_vessel
            )

    def get_steps(self) -> Optional[List[Step]]:
        """Get the list of steps/base steps to execute.

        Returns:
            Optional[List[Step]]: Steps to execute. None if no flush vessel.
        """

        # Using a flush tube vessel, get movement step
        if self.flush_tube_vessel:
            return [
                CMove(
                    from_vessel=self.flush_tube_vessel,
                    to_vessel=self.to_vessel,
                    to_port=self.to_port,
                    through=self.through_cartridge,
                    dispense_speed=self.dispense_speed,
                    volume=DEFAULT_AIR_FLUSH_TUBE_VOLUME
                )
            ]

        # No flush vessel, empty
        return []

class Transfer(ChemputerStep, AbstractTransferStep):
    """Transfer contents of one vessel to another.

    Args:
        from_vessel (str): Vessel name to transfer from.
        to_vessel (str): Vessel name to transfer to.
        volume (float): Volume to transfer in mL.
        from_port (str): Port on from_vessel to transfer from.
        to_port (str): Port on to_vessel to transfer from.
        through (str): Node name to transfer to.
        aspiration_speed (float): Speed in mL / min to pull liquid out of
            from_vessel.
        move_speed (float): Speed in mL / min to move liquid at.
        dispense_speed (float): Speed in mL / min to push liquid out of pump
            into to_vessel.
        rinse_withdrawal_excess (Optional[float]): specifies % excess volume to
            be aspirated after rinse steps. Expressed as a decimal fraction in
            range 0 -> 1. Defaults to 0.2 (i.e. 20 % excess).
        through_cartridge (str): Internal property. Cartridge to pass through.
        stir (Optional[bool]): True to stir to_vessel during transfer. Defaults
            to False.
        stir_rinse (Optional[bool]): True to stir during rinse steps. Defaults
            to True.
        stir_speed (Optional[float]): stirring speed (in RPM). Only used if stir
            or rinse_stir == True. Defaults to 250 RPM.
        rinse_stir_time (Optional[float]): time to continue stirring from_vessel
            after rinsing. Defaults to 30 seconds.
        rinse_settle_time (Optional[float]): time to leave from_vessel to settle
            after stirring, rinsing. Defaults to 10 seconds.
    """

    DEFAULT_PROPS = {
        'stir_to_vessel': False,
        'stir_from_vessel': False,
        'rinse_stir': True,
        'rinse_stir_time': '30 seconds',
        'rinse_settle_time': '10 seconds',
        'stir_speed': '250 RPM',
        'aspiration_speed': 40,  # mL / min
        'dispense_speed': 40,  # mL / min
        'move_speed': 40,  # mL / min
        'viscous': False,
        'flush_tubing': False,
        'from_port': None,
        'to_port': None,
        'through': None,
        'time': None,
        'rinsing_solvent': None,
        'rinsing_volume': None,
        'rinsing_repeats': 1,
        'rinse_withdrawal_excess': 0.2,
        'unlock_after': False,
    }

    INTERNAL_PROPS = [
        'through_cartridge',
        'transfer_all',
        'from_vessel_has_stirrer',
        'from_vessel_has_heater',
        'from_vessel_has_chiller',
        'rinsing_solvent_vessel',
        'to_vessel_has_stirrer'
    ]

    PROP_TYPES = {
        'stir_to_vessel': bool,
        'stir_from_vessel': bool,
        'rinse_stir': bool,
        'stir_speed': float,
        'from_vessel': VESSEL_PROP_TYPE,
        'to_vessel': VESSEL_PROP_TYPE,
        'volume': float,
        'from_port': PORT_PROP_TYPE,
        'to_port': PORT_PROP_TYPE,
        'through': str,
        'time': float,
        'aspiration_speed': float,
        'move_speed': float,
        'dispense_speed': float,
        'viscous': bool,
        'through_cartridge': str,
        'transfer_all': bool,
        'from_vessel_has_stirrer': bool,
        'from_vessel_has_heater': bool,
        'from_vessel_has_chiller': bool,
        'flush_tubing': bool,
        'rinsing_solvent': REAGENT_PROP_TYPE,
        'rinsing_volume': float,
        'rinsing_repeats': int,
        'rinsing_solvent_vessel': str,
        'rinse_withdrawal_excess': float,
        'to_vessel_has_stirrer': bool,
        'rinse_stir_time': float,
        'rinse_settle_time': float,
        'unlock_after': bool,
    }

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'from_port': PORT_PROP_LIMIT,
        'to_port': PORT_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'rinsing_volume': VOLUME_PROP_LIMIT,
    }

    def __init__(
        self,
        from_vessel: str,
        to_vessel: str,
        volume: float,
        rinsing_solvent: Optional[str] = 'default',
        rinsing_volume: Optional[float] = 'default',
        rinsing_repeats: Optional[int] = 'default',
        from_port: Optional[str] = 'default',
        to_port: Optional[str] = 'default',
        through: Optional[str] = 'default',
        time: Optional[float] = 'default',
        aspiration_speed: Optional[float] = 'default',
        move_speed: Optional[float] = 'default',
        dispense_speed: Optional[float] = 'default',
        viscous: Optional[bool] = 'default',
        flush_tubing: Optional[bool] = 'default',
        rinse_withdrawal_excess: Optional[float] = 'default',
        stir_to_vessel: Optional[bool] = 'default',
        stir_from_vessel: Optional[bool] = 'default',
        rinse_stir: Optional[bool] = 'default',
        stir_speed: Optional[float] = 'default',
        rinse_stir_time: Optional[float] = 'default',
        rinse_settle_time: Optional[float] = 'default',
        unlock_after: Optional[bool] = 'default',

        # Internal properties
        through_cartridge: Optional[str] = None,
        transfer_all: Optional[bool] = False,
        from_vessel_has_stirrer: Optional[bool] = False,
        from_vessel_has_heater: Optional[bool] = None,
        from_vessel_has_chiller: Optional[bool] = None,
        rinsing_solvent_vessel: Optional[str] = None,
        to_vessel_has_stirrer: Optional[bool] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph) -> str:
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        if self.volume == 'all':
            self.transfer_all = True

        # Obtain the through cartridge if not defined
        if not self.through_cartridge and self.through:
            self.through_cartridge = get_cartridge(graph, self.through)

        # Obtain the to port if not defined
        if self.to_port in [None, ''] and self.to_vessel:
            # Get the vessel class of the to_vessel
            to_class = graph.nodes[self.to_vessel]['class']

            # Ports are present in default ports, set them
            if to_class in DEFAULT_PORTS:
                self.to_port = DEFAULT_PORTS[to_class]['to']

        # Check if the from vessel has a stirrer attached
        self.from_vessel_has_stirrer = (
            True if get_vessel_stirrer(graph, self.from_vessel) else False
        )

        #  Check if the to vessel has a stirrer attached
        self.to_vessel_has_stirrer = (
            True if get_vessel_stirrer(graph, self.to_vessel) else False
        )

        # From vessel is defined
        if self.from_vessel:
            # Get the vessel class from the graph
            from_class = graph.nodes[self.from_vessel]['class']

            # Get teh ports if not defined
            if self.from_port in [None, ''] and self.from_vessel:
                # Vessel class is present in default ports, set it
                if from_class in DEFAULT_PORTS:
                    self.from_port = DEFAULT_PORTS[from_class]['from']

            # Ge the heater and the chiller
            heater, chiller = get_heater_chiller(graph, self.from_vessel)

            # Check heater is present
            if self.from_vessel_has_heater is None:
                self.from_vessel_has_heater = True if heater else False

            # Check chiller is present
            if self.from_vessel_has_chiller is None:
                self.from_vessel_has_chiller = True if chiller else False

        if self.rinsing_solvent:
            self.rinsing_solvent_vessel = get_reagent_vessel(
                graph, self.rinsing_solvent)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        return (
            self.get_pre_stir_steps()
            + self.get_move_steps()
            + self.get_flush_tubing_steps()
            + self.get_rinse_steps()
            + self.get_stop_heatchill_steps()
            + self.get_post_stir_steps()
        )

    def get_rinse_steps(self) -> Optional[List[Step]]:
        if self.rinsing_solvent is not None:

            # Get the pump speeds
            dispense_speed = self.get_dispense_speed()
            aspiration_speed = self.get_aspiration_speed()

            #  as rinsing is often used to remove residual solid or solution,
            #  assume the volume of rinsing solvent will be greater than the
            #  solvent added for rinsing. Assume a lower cut-off of 2 mL for
            #  final volume of rinsing solvent + residual solid / solution in
            #  vessel
            withdrawal_volume = max(self.rinsing_volume + (
                self.rinsing_volume * self.rinse_withdrawal_excess), 2)

            #  core rinse steps for Repeat
            children = [
                CMove(
                    from_vessel=self.rinsing_solvent_vessel,
                    to_vessel=self.from_vessel,
                    to_port=self.from_port,
                    volume=self.rinsing_volume,
                ),
                CMove(
                    from_vessel=self.from_vessel,
                    from_port=self.from_port,
                    to_vessel=self.to_vessel,
                    to_port=self.to_port,
                    volume=withdrawal_volume,
                    through=self.through_cartridge,
                    aspiration_speed=aspiration_speed,
                    move_speed=self.move_speed,
                    dispense_speed=dispense_speed
                )
            ]

            #  Apply rinse stirring steps if specified
            if self.rinse_stir:
                if self.from_vessel_has_stirrer:

                    #  start stirring from_vessel
                    start_stir = [
                        StartStir(
                            vessel=self.from_vessel,
                            stir_speed=self.stir_speed
                        )
                    ]
                    #  wait for 30 seconds after rinsing solvent added
                    wait_stop = [Wait(self.rinse_stir_time)]
                    if not self.stir_from_vessel:
                        #  stop stirring, then wait a further 10 seconds
                        #  to allow the solvent to settle
                        wait_stop.extend([
                            StopStir(vessel=self.from_vessel),
                            Wait(self.rinse_settle_time)
                        ])

                    #  start stirring, add rinsing solvent, wait-StopStir-wait,
                    #  then finally remove rinsing solvent
                    children = (
                        start_stir
                        + children[0:1]
                        + wait_stop
                        + children[1::]
                    )

            return [
                Repeat(
                    repeats=self.rinsing_repeats,
                    children=children
                )
            ]
        return []

    def get_move_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        # Get the pump speeds
        dispense_speed = self.get_dispense_speed()
        aspiration_speed = self.get_aspiration_speed()

        return [
            CMove(
                from_vessel=self.from_vessel,
                from_port=self.from_port,
                to_vessel=self.to_vessel,
                to_port=self.to_port,
                volume=self.volume,
                through=self.through_cartridge,
                aspiration_speed=aspiration_speed,
                move_speed=self.move_speed,
                dispense_speed=dispense_speed,
                unlock_after=self.unlock_after
            )
        ]

    def get_flush_tubing_steps(self) -> Optional[List[Step]]:
        """Get the list of steps/base steps to execute.

        Returns:
            Optional[List[Step]]: Steps to execute. Noen if flushing not
                                    required.
        """

        # Return flush step if required, else []
        return [
            FlushTubing(
                to_vessel=self.to_vessel,
                to_port=self.to_port,
                through_cartridge=self.through_cartridge,
                dispense_speed=self.get_dispense_speed(),
            )
        ] if self.flush_tubing else []

    def get_pre_stir_steps(self) -> Optional[List[Step]]:
        """Get initial stir steps to stop stirring from_vessel and start
        stirring to_vessel

        Returns:
            Optional[List[Step]]: initial stir steps, else []
        """
        pre_stir_steps = []

        # Set stirring in the from_vessel
        if self.from_vessel_has_stirrer:
            if self.stir_from_vessel:
                pre_stir_steps.append(
                    StartStir(
                        vessel=self.from_vessel,
                        stir_speed=self.stir_speed
                    ))
            else:
                pre_stir_steps.append(StopStir(self.from_vessel))

        #  start stirring to_vessel if stir and to_vessel has a stirrer attached
        if self.to_vessel_has_stirrer:
            if self.stir_to_vessel:
                pre_stir_steps.append(
                    StartStir(
                        vessel=self.to_vessel,
                        stir_speed=self.stir_speed
                    )
                )
            else:
                pre_stir_steps.append(StopStir(self.to_vessel))

        return pre_stir_steps

    def get_post_stir_steps(self) -> Optional[List[Step]]:
        """Get final stir steps to stop stirring all vessels as needed.

        Returns:
            Optional[List[Step]]: initial stir steps, else []
        """
        post_stir_steps = []

        # Stop stirring from_vessel if a stirrer is attached.
        if self.from_vessel_has_stirrer:
            post_stir_steps.append(StopStir(self.from_vessel))

        # Stop stirring to_vessel if a stirrer is attached.
        if self.to_vessel_has_stirrer:
            post_stir_steps.append(StopStir(self.to_vessel))

        return post_stir_steps

    def get_stop_heatchill_steps(self) -> Optional[List[Step]]:
        """Get the StopHeatChill steps if heater or chiller present

        Returns:
            Optional[List[Step]]: StopHeatChill step if required, else []
        """

        # have either a heater or chiller, stop them
        if self.from_vessel_has_heater or self.from_vessel_has_chiller:
            return [StopHeatChill(vessel=self.from_vessel)]

        # No heater or chiller attached
        return []

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.from_vessel and node_in_graph(
                    graph, self.from_vessel),
                error_msg='from_vessel must be node in graph.',
            ),
            SanityCheck(
                condition=self.to_vessel and node_in_graph(
                    graph, self.to_vessel),
                error_msg='to_vessel must be node in graph.'
            ),
            SanityCheck(
                condition=not self.through or self.through_cartridge,
                error_msg=f'Trying to transfer through "{self.through}" but cannot find\
 cartridge containing {self.through}.'
            )
        ]

    def get_dispense_speed(self) -> float:
        """Calculates the dispensing speed of the pumps
        Dispense Speed (mL / min) = (Volume(ml) / time(min))

        Returns:
            float: Dispensing speed of the pump
        """

        if self.time and type(self.volume) != str:
            return self.volume / (self.time / 60)

        return self.dispense_speed

    def get_aspiration_speed(self) -> float:
        """Get the aspiration speed of the pump.
        Speed dependent on whether the solution is viscous or not

        Returns:
            float: Aspiration speed of the pump
        """

        return (
            self.aspiration_speed if not self.viscous
            else DEFAULT_VISCOUS_ASPIRATION_SPEED
        )
