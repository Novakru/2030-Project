from typing import Union, Dict
from ....execution.abstract_executor import AbstractXDLExecutor
from ..steps import Add, CBTurnWheel
from ....errors import XDLError

N_WHEEL_POSITIONS = 24

class ModularWheelExecutor(AbstractXDLExecutor):

    def map_vessels(self):
        vessel_map = {}
        i = 0
        for step in self._xdl.steps:
            if type(step) == Add:
                if step.vessel not in vessel_map:
                    vessel_map[step.vessel] = i
                    i += 1
                    if i > N_WHEEL_POSITIONS:
                        raise XDLError(f'Too many vessels for number of wheel\
 positions {i} - {N_WHEEL_POSITIONS}')
        for step in self._xdl.steps:
            if type(step) == Add:
                step.vessel = vessel_map[step.vessel]

    def fill_in_add_step_n_turns(self):
        """Fill in the number of turns each add step requires to get to the
        specified position based on the wheel position from the previous steps.
        """
        wheel_position = 0
        for step in self._xdl.steps:
            # Add step, fill in n_turns and increment wheel position variable.
            if type(step) == Add:
                # Fill in n_turns property
                step.n_turns = step.vessel - wheel_position
                if step.n_turns < 0:
                    step.n_turns += N_WHEEL_POSITIONS

                # Increment wheel positon
                wheel_position += step.n_turns
                if wheel_position > N_WHEEL_POSITIONS:
                    wheel_position -= N_WHEEL_POSITIONS

            # CBTurnWheel base step, increment wheel position variable.
            elif type(step) == CBTurnWheel:
                # Increment wheel position
                wheel_position += step.n_turns
                if wheel_position > N_WHEEL_POSITIONS:
                    wheel_position -= N_WHEEL_POSITIONS

    def prepare_for_execution(
        self,
        graph_file: Union[str, Dict],
        interactive: bool = True,
        save_path: str = '',
        sanity_check: bool = True,
    ) -> None:
        """At the moment just figures out how many turns of the wheel are
        required.
        """
        self.map_vessels()
        self.fill_in_add_step_n_turns()
        self._prepared_for_execution = True
