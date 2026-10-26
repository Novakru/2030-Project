# Std
from typing import List

# Other
import termcolor

# Relative
from .core.step import Step
from .utils import pretty_props_table


def start_executing_step_msg(
        step: Step, step_indexes: List[int] = []) -> str:
    """Return strings to log when step begins executing.

    Args:
        step (Step): Step beginning execution.
        step_indexes (List[int]): Indexes into steps list and substeps lists.

    Returns:
        str: Log message for when the step begins executing.
    """
    # First line, e.g. "Executing step 2.3.1"
    step_index_str = '.'.join([str(idx + 1) for idx in step_indexes])
    first_line = termcolor.colored(
        f'Executing step {step_index_str}:', color='green', attrs=['bold'])

    # Step human readable description
    human_readable = termcolor.colored(
        f'{step.human_readable()}.', attrs=['bold'])

    # Step name
    step_name = termcolor.colored(step.name, color='cyan', attrs=['bold'])

    # Step properties table
    prop_table = termcolor.colored(
        pretty_props_table(step.properties), color='cyan')

    # Combine all message parts and return
    return f'{first_line}\n{human_readable}\n{step_name}\n{prop_table}\n'

def finished_executing_step_msg(step: Step, step_indexes: List[int]) -> str:
    """Message to log when step finishes executing.

    Args:
        step (Step): Step that has finished executing.
        step_indexes (List[int]): Indexes into steps list and substeps lists.

    Returns:
        str: Log message for when step finishes executing.
    """
    step_index_str = '.'.join([
        str(idx + 1) for idx in step_indexes])
    return termcolor.colored(
        f'Finished executing step {step_index_str} ',
        color='green', attrs=['bold'],
    ) + termcolor.colored(step.name, color='cyan', attrs=['bold']) + '\n'
