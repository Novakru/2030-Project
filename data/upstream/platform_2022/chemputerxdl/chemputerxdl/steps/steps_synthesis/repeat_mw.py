"""
.. module:: steps_synthesis.repeat_cleanmw
    :platforms: Unix, Windows
    :synopsis: XDL step for vial tracking and auto-cleaning with MWAddAndTurn.
"""
import copy

from typing import Optional, List, Union, Tuple
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import Step, AbstractStep
from xdl.utils.misc import SanityCheck

# Relative
from ..base_step import ChemputerStep
from ..steps_utility import MWAddAndTurn, HarvestWheel
from ..steps_base import CTurnMotor
from ...utils.execution import (
    get_reagent_vessel,
    node_in_graph,
    get_mw_positions,
    get_modular_motors
)

class RepeatCleanMW(ChemputerStep, AbstractStep):
    """
    Step for repeating blocks of steps containing MWAddAndTurn steps. MW sample
    tube cleans are inserted, with cleaning solution dispensed to waste vial.

    Args:
        repeats (int): number of times to execute child steps, with MW cleans.
        n_positions (int): number of vial positions in wheel. Defaults to 20.
        cleaning_solvent (str): solvent to use for MW cleans.
        start_position (int, optional): starting vial position on wheel.
        waste_vial (int, optional): vial designated for waste.
        mw_clean_volume (int, optional): volume of cleaning solution to
            dispense to waste during every MW clean. Defaults to 1 mL.
        flush (bool, optional): specifies whether to flush modular wheel
            sampling tube with air or inert gas after cleaning step. Defaults
            to False.
    """
    DEFAULT_PROPS = {
        'repeats': 1,  # Number of times to perform child steps
        'waste_vial': 1,  # position of allocated waste vial in Modular Wheel
        'mw_clean_volume': 1,  # volume to use to clean MW sample tube
        'start_position': 1,  # starting position of Modular Wheel
        'flush': False,  # Flush sample tube with gas after cleans if True
    }

    PROP_TYPES = {
        'children': Union[Step, List[Step]],
        'repeats': int,
        'waste_vial': int,
        'mw_clean_volume': float,
        'start_position': int,
        'n_positions': int,
        'cleaning_solvent': str,
        'flush': bool,
        'cleaning_vessel': str,
        'motor_steps': int
    }

    INTERNAL_PROPS = [
        'cleaning_vessel', 'n_positions', 'motor_steps'
    ]

    def __init__(
        self,
        cleaning_solvent: str,
        children: Union[Step, List[Step]],
        repeats: Optional[int] = 'default',
        waste_vial: Optional[int] = 'default',
        mw_clean_volume: Optional[float] = 'default',
        start_position: Optional[int] = 'default',
        flush: Optional[bool] = 'default',

        #  INTERNAL PROPS
        cleaning_vessel: Optional[str] = None,
        n_positions: Optional[int] = None,
        motor_steps: Optional[int] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

        # Convert `children` to list if not already
        if type(children) != list:
            self.children = [children]

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        if not self.cleaning_vessel:
            self.cleaning_vessel = get_reagent_vessel(
                graph=graph,
                reagent=self.cleaning_solvent
            )

        if not self.n_positions:
            self.n_positions = get_mw_positions(graph)

        if not self.motor_steps:
            self.motor_steps = get_modular_motors(
                graph)['modular_wheel_increments']

    def get_steps(self) -> List[Step]:
        """
        Builds repeat steps, inserting MW cleans and changing turns where
        needed to avoid dispensing sample into waste vial or vice versa.

        Args:
            steps (List[step]): list of child steps.

        Returns:
            List[Step]: list of child steps with repeats, clean steps added.
        """

        final_steps = []

        if self.n_positions is None:
            return final_steps

        #  ensure starting position is set, keep track of whether first
        #  MWAddAndTurn or CTurnMotor step is initialized at waste
        initialized = False
        position = self.start_position

        #  keep track of wheel direction, arbitrarily assigning start as
        #  forward direction
        forward = True

        #  execute children N times (N = self.repeats)
        for i in range(self.repeats):
            for step in self.children:

                #  list of modified steps for children and any additional MW
                #  cleaning steps
                modified_steps = []
                step = copy.deepcopy(step)

                #  check if step affects modular wheel - keep track of vial
                #  position but also insert cleaning step if necessary
                if type(step) in [MWAddAndTurn, CTurnMotor, HarvestWheel]:
                    turns = step.n_turns

                    #  after first cycle, wheel will always be at position for
                    #  next sample
                    if initialized:
                        step.n_turns = 0
                    initialized = True

                    #  ensure no sample is ever added to designated waste vial
                    if position == self.waste_vial:
                        step.turn_first = True
                        step.n_turns = turns
                        if step.n_turns == 0:
                            step.n_turns += 1
                        position = self.correct_position(
                            position + step.n_turns)

                    modified_steps.append(step)

                    #  get shortest route on wheel to waste vial
                    clean_turns, reverse = self.get_shortest_turn(
                        (position, self.waste_vial))

                    #  keep wheel direction consistent
                    if forward is False:
                        reverse = not reverse

                    #  turn to waste vial and dispense cleaning solution
                    modified_steps.append(
                        self.add_mw_clean(
                            mw_step=step, n_turns=clean_turns, reverse=reverse)
                    )

                    #  correct wheel direction and vial position if necessary
                    if step.reverse_first:
                        forward = not forward
                    if forward:
                        position = self.correct_position(position + turns)
                    else:
                        position = self.correct_position(position - turns)
                    if step.reverse_after:
                        forward = not forward

                    #  work out fastest route and direction to get to next
                    #  sample vial on wheel
                    turns, reverse = self.get_shortest_turn(
                        (self.waste_vial, position)
                    )

                    #  keep wheel direction consistent
                    if forward is False:
                        reverse = not reverse

                    modified_steps.append(
                        self.return_from_waste(
                            mw_step=step,
                            n_turns=turns,
                            reverse=reverse
                        )
                    )

                else:
                    modified_steps.append(step)

                final_steps.extend(modified_steps)

        return final_steps

    def add_mw_clean(
        self,
        mw_step: MWAddAndTurn,
        n_turns: int,
        reverse: bool
    ) -> MWAddAndTurn:
        """Get MWAddAndTurn step for cleaning - make n_turns to designated
        waste vial and dispense cleaning solution.

        Args:
            mw_step (MWAddAndTurn): MWAddAndTurn step that requires
                post-cleaning.
            n_turns (int): number of turns to make to reach waste.
            reverse (bool): True to reverse before / after turns, False to
                turn without reversing wheel direction.

        Returns:
            MWAddAndTurn: step to turn to waste and dispense cleaning solution.
        """
        return MWAddAndTurn(
            from_vessel=self.cleaning_vessel,
            volume=self.mw_clean_volume,
            n_turns=n_turns,
            reverse_first=reverse,
            reverse_after=reverse,
            turn_first=True,
            wait_turn=mw_step.wait_turn,
            wait_reverse=mw_step.wait_reverse,
            aspiration_speed=mw_step.aspiration_speed,
            dispense_speed=mw_step.dispense_speed,
            move_speed=mw_step.move_speed,
            flush=self.flush
        )

    def return_from_waste(
        self,
        mw_step: MWAddAndTurn,
        n_turns: int,
        reverse: bool
    ) -> CTurnMotor:
        """Get CTurnMotor step required post-cleaning - make n_turns from waste
        vial to next sampling vial in wheel.

        Args:
            mw_step (MWAddAndTurn): MWAddAndTurn step that requires
                post-cleaning.
            n_turns (int): number of turns to make to reach waste.
            reverse (bool): True to reverse before / after turns, False to
                turn without reversing wheel direction.

        Returns:
            CTurnMotor: CTurnMotor step for returning to next sample vial
                position in wheel.
        """
        return CTurnMotor(
            device_name=mw_step.motor_name,
            motor_name=mw_step.motor_name,
            n_turns=n_turns,
            reverse_first=reverse,
            reverse_after=reverse,
            wait_turn=mw_step.wait_turn,
            wait_reverse=mw_step.wait_reverse,
            increment=self.motor_steps
        )

    def correct_position(self, position: int) -> int:
        """
        Corrects vial position if > self.n_positions or < 1.
        Args:
            position (int): MW vial position.

        Returns:
            int: corrected MW vial position
        """
        if position > self.n_positions:
            position = position % self.n_positions
        elif position < 1:
            position += self.n_positions + position
        return position

    def get_shortest_turn(self, positions: Tuple[int]) -> Tuple[int, bool]:
        """
        Works out the shortest number of turns between two positions in the
        modular wheel, and whether the fastest route is in the forward or
        reverse direction.

        Args:
            positions (Tuple[int]): (start (int), target (int)) where start =
                starting vial position and target = target vial position to
                move to.

        Returns:
            Tuple[int, bool]: n_turns (int), reverse_first (bool) where n_turns
                = number of turns to make on wheel. reverse_first = True to
                reverse wheel direction for turns, False to if not.
        """

        #  get minimum distance between current and target vial positions
        diff = abs(positions[1] - positions[0])

        #  work out the minimum number of turns to make to reach target from
        #  current vial position, and whether the wheel direction should be
        #  reversed first
        if positions[1] > positions[0]:
            if diff < self.n_positions / 2:
                n_turns = diff
                reverse_first = False
            else:
                reverse_first = True
                n_turns = self.n_positions - diff
        else:
            if diff < self.n_positions / 2:
                n_turns = diff
                reverse_first = True
            else:
                reverse_first = False
                n_turns = self.n_positions - diff

        return n_turns, reverse_first

    def human_readable(self, language: Optional[str] = 'en') -> str:
        """Gets the human-readable text for this step.

        Args:
            language (Optional[str], optional): Localisation language.
                                                Defaults to 'en'.

        Returns:
            str: Human-readable text for the step
        """

        human_readable = 'Repeat with MWAddAndTurn:\n'

        # Add human readable text for each child step
        for step in self.children:
            human_readable += f'    {step.human_readable()}\n'

        return human_readable

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.cleaning_vessel and node_in_graph(
                    graph, self.cleaning_vessel),
                error_msg="cleaning_vessel must be node in the graph"
            ),
            SanityCheck(
                condition=self.n_positions and self.n_positions > 0,
                error_msg="must define vial positions for wheel in graph"
            )
        ]
