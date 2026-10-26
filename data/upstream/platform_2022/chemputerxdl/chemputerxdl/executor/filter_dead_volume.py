import time
from typing import List, Dict, Tuple
from networkx import MultiDiGraph

# XDL
from xdl.utils.logging import get_logger
from xdl.steps import Step
from xdl.hardware import Hardware

# Relative
from .errors import XDLNoSolventsError
from .cleaning import (
    get_available_solvents, get_cleaning_chunks, get_cleaning_schedule)
from .utils import VesselContents
from .tracking import iter_vessel_contents
from ..constants import (
    FILTER_DEAD_VOLUME_LIQUID_METHOD,
    FILTER_DEAD_VOLUME_INERT_GAS_METHOD,
    CHEMPUTER_FILTER,
    BOTTOM_PORT,
)
from ..steps import AddFilterDeadVolume, RemoveFilterDeadVolume, CConnect
from ..utils.execution import graph_filters, get_vacuum_configuration

# Just for type annotations
if False:
    from xdl import XDL

################################
# Inert Gas Dead Volume Method #
################################

def add_filter_inert_gas_connect_steps(
    graph: MultiDiGraph, steps: List[Step]
) -> None:
    """Add steps to self._xdl.steps to implement the following:
    1) Connection of inert gas to bottom of filter flasks at start of
    procedure.
    """
    # Connect inert gas to bottom of filter flasks at start of procedure.
    for filter_vessel in graph_filters(graph):
        # Get the vacuum config
        vacuum_info = get_vacuum_configuration(
            graph,
            filter_vessel
        )

        # Connect to inert gas if defined in config
        if vacuum_info['valve_inert_gas']:
            steps.insert(
                0,
                CConnect(
                    from_vessel=vacuum_info['valve_inert_gas'],
                    to_vessel=filter_vessel,
                    to_port=BOTTOM_PORT
                )
            )

#############################
# Liquid Dead Volume Method #
#############################

def get_filter_emptying_steps(
    graph_hardware: Hardware, steps: List[Step]
) -> List[Tuple[int, str, Dict[str, VesselContents]]]:
    """Get steps at which a filter vessel is emptied. Also return full
    list of vessel contents dict at every step.

    Returns:
        List[Tuple[int, str, Dict[str, VesselContents]]]: List of tuples,
            format: [(step_index,
                        filter_vessel_name,
                        {vessel: VesselContents, ...})...]
    """

    # Empty collections for storing information
    filter_emptying_steps = []
    full_vessel_contents = []
    prev_vessel_contents = {}

    # Iterate through each vessel's contents
    for i, _, vessel_contents, _ in iter_vessel_contents(
        steps, graph_hardware
    ):
        # Add current cessens contents to list
        full_vessel_contents.append(vessel_contents)

        # Iterate through the vessel's contents
        for vessel, contents in vessel_contents.items():
            if (graph_hardware[vessel].type == CHEMPUTER_FILTER
                    and vessel in prev_vessel_contents):
                # If filter vessel has just been emptied, append to filters.
                if (not contents.reagents
                        and prev_vessel_contents[vessel].reagents):
                    filter_emptying_steps.append(
                        (i, vessel, full_vessel_contents))

        prev_vessel_contents = vessel_contents

    return filter_emptying_steps

def get_filter_dead_volume(
    graph: MultiDiGraph, filter_vessel: str
) -> float:
    """Return dead volume (volume below filter) of given filter vessel.

    Args:
        filter_vessel (str): ID of filter vessel.

    Returns:
        float: Dead volume of given filter vessel.
    """

    # Iterate through vessels in hardware
    for vessel, data in graph_filters(graph, data=True):
        # Vessel is present, return dead volume
        if vessel == filter_vessel:
            return data['dead_volume']

    return 0

def add_implied_add_dead_volume_steps(
    graph: MultiDiGraph,
    graph_hardware: Hardware,
    xdl_obj: 'XDL'
) -> None:
    """
    Add AddFilterDeadVolume steps if filter top is being used, to fill up the
    bottom of the filter with solvent, so material added to the top doesn't
    drip through.

    Raises:
        AttributeError: If filter_dead_volume_method is liquid, but
            self._xdl has no filter_dead_volume_solvent attribute.
    """

    # Get list of the cleaning solvents
    cleaning_solvents = get_cleaning_schedule(xdl_obj)

    # Take the first one present or just assign empty list
    cleaning_solvents = (
        cleaning_solvents[0] if len(cleaning_solvents) > 1 else []
    )

    # Find steps at which a filter vessel is emptied. Can't just look for
    # Filter steps as liquid may be transferred to filter flask for other
    # reasons i.e. using the chiller.
    for filter_i, filter_vessel, full_vessel_contents in reversed(
        get_filter_emptying_steps(
            graph_hardware, xdl_obj.steps
        )
    ):
        j = filter_i - 1

        # Find point at which first reagent is added to filter vessel.
        # This is the point at which to insert the PrepareFilter step.
        while (j > 0
                and filter_vessel in full_vessel_contents[j - 1]
                and full_vessel_contents[j - 1][filter_vessel].reagents):
            j -= 1

        if cleaning_solvents is None:
            raise XDLNoSolventsError(
                'No solvents available for filter dead volume'
            )

        solvent = cleaning_solvents[j]

        # Insert AddFilterDeadVolume step into self._xdl.steps.
        xdl_obj.steps.insert(j, AddFilterDeadVolume(
            filter_vessel=filter_vessel, solvent=solvent,
            volume=get_filter_dead_volume(graph, filter_vessel)))

def add_implied_remove_dead_volume_steps(
    graph: MultiDiGraph,
    graph_hardware: Hardware,
    xdl_obj: 'XDL'
) -> None:
    """When liquid is transferred from a filter vessel remove dead volume
    first.
    """
    # Look for filter emptying steps and add RemoveFilterDeadVolume step
    # just before them.
    for i, vessel, _ in reversed(get_filter_emptying_steps(
            graph_hardware, xdl_obj.steps)):
        # Only move to waste after Filter step. For any other step should
        # become part of the reaction mixture.
        if xdl_obj.steps[i].name == 'Filter':
            xdl_obj.steps.insert(
                i,
                RemoveFilterDeadVolume(
                    filter_vessel=vessel,
                    dead_volume=get_filter_dead_volume(graph, vessel)
                )
            )

####################
# CLI Confirmation #
####################

def confirm_dead_volume_handling_behaviour(filter_dead_volume_method) -> None:
    """Prompts for the user to indicate that the suggested behaviour is valid.
    If invalid, user an opt to change
    """
    choice = FILTER_DEAD_VOLUME_LIQUID_METHOD

    # Build verification message
    msg = '\n  Filter dead volume is currently handled by'
    msg += f' {filter_dead_volume_method}.'
    msg += '\n  Would you like to switch dead the volume handling method?'
    msg += ' (y, [n])\n'

    # Prompt the user to select appropriate conditions
    verify = None
    while verify not in ['y', 'n', '']:
        verify = input(msg)

        # User wishes to verify
        if verify == 'y':
            available_methods = [
                FILTER_DEAD_VOLUME_LIQUID_METHOD,
                FILTER_DEAD_VOLUME_INERT_GAS_METHOD
            ]

            # Get correct choice from user
            choice = None
            while choice not in available_methods:
                msg = '\n Please select desired method:'
                msg += f'\n    {FILTER_DEAD_VOLUME_LIQUID_METHOD}'
                msg += f'\n    {FILTER_DEAD_VOLUME_INERT_GAS_METHOD}\n'
                choice = input(msg)

    # Set to the user's choice
    return choice

def confirm_dead_volume_solvents(xdl_obj):
    """Allow user to see filter dead volume steps being added and make
    changes to what solvents are used.
    """

    # Build verification message
    msg = '\n  Would you like to review dead volume solvents?'
    msg += ' (y, [n])\n'

    # Prompt the user to make a selection
    verify = None
    while verify not in ['y', 'n', '']:
        verify = input(msg)

    # Verification selected
    if verify:
        logger = get_logger()
        logger.info('\n\nVerifying AddFilterDeadVolume Steps\n------\
---------------------------------------\n')
        logger.info('* indicates the step which is being verified. \
Other steps are shown for context.\n\n')

        # Get solvents available
        solvents = get_available_solvents(xdl_obj)

        # Add cleaning steps
        chunks = get_cleaning_chunks(
            xdl_obj,
            step_type=AddFilterDeadVolume
        )
        logger.info('Procedure Start')

        # Iterate through each added cleaning step
        for chunk in chunks:
            # Iterate through the step and log based on selections
            for i in range(len(chunk)):
                if type(chunk[i]) == AddFilterDeadVolume:
                    logger.info('---------------\n')
                    for j, step in enumerate(chunk):
                        if j == i:
                            logger.info(
                                f'* AddFilterDeadVolume {step.solvent}'
                            )
                        elif type(step) == AddFilterDeadVolume:
                            logger.info(
                                f'AddFilterDeadVolume {step.solvent}'
                            )
                        else:
                            logger.info(step.human_readable())

                    answer = None
                    # Get appropriate answer.
                    while answer not in ['', 'y', 'n']:
                        answer = input(
                            f'\nIs {chunk[i].solvent} an appropriate dead \
volume solvent? ([y], n)\n')
                    # Leave solvent as is. Move onto next steps.
                    if not answer or answer == 'y':
                        continue
                    # Get user to select new solvent.
                    else:
                        new_solvent_index = None
                        # Wait for user to give appropriate input.
                        while new_solvent_index not in list(
                                range(len(solvents))):
                            input_msg = 'Select new solvent by number\n'
                            input_msg += '\n'.join(
                                [f'{solvent} ({i})'
                                    for i, solvent in enumerate(solvents)]
                            ) + '\n'
                            new_solvent_index = input(input_msg)
                            try:
                                new_solvent_index = int(new_solvent_index)
                            except ValueError:
                                logger.info('Input must be number \
corresponding to solvent.')
                        # Change step solvent.
                        chunk[i].solvent = solvents[new_solvent_index]
                        logger.info(
                            f'Solvent changed to {chunk[i].solvent}\n'
                        )
                        time.sleep(1)
