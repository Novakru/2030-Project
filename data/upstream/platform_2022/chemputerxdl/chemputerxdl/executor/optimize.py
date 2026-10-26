from typing import List
from networkx import MultiDiGraph

# Chemputer stack
from xdl.steps import (
    Step, AbstractBaseStep, AbstractStep, NON_RECURSIVE_ABSTRACT_STEPS)
from xdl.hardware import Hardware
from xdl.constants import INERT_GAS_SYNONYMS
from chempiler import Chempiler

# Relative
from .tracking import iter_vessel_contents
from .constants import CLEAN_BACKBONE_STEP_TYPES
from .utils import is_aqueous
from ..steps import (
    CleanBackbone,
    Dry,
    StartStir,
    StopStir,
    Add,
    Filter,
    Separate,
    ResetHandling
)
from ..utils.execution import get_waste_on_valve, get_backbone
from ..constants import CHEMPUTER_VALVE

############
# Cleaning #
############

def optimize_backbone_cleaning(
    graph: MultiDiGraph,
    chempiler: Chempiler,
    steps: List[Step] = None
) -> None:
    """Only clean backbone valves that have been affected by previous steps.
    """

    valves_used = []
    n_clean_backbone_steps = len([
        step for step in steps if type(step) in CLEAN_BACKBONE_STEP_TYPES
    ])
    ignore_first_and_last = [0, n_clean_backbone_steps - 1]
    i = 0
    for step in steps:
        if type(step) in CLEAN_BACKBONE_STEP_TYPES:
            clean_backbone_step = step
            if type(step) == ResetHandling:
                clean_backbone_step = step.steps[0]

            if i in ignore_first_and_last:
                i += 1
                continue

            i += 1

            backbone = get_backbone(graph, ordered=True)

            # Find optimum start valve
            for valve in backbone:
                if (valve in valves_used
                        or valve == clean_backbone_step.solvent_valve):

                    # Need to check if waste on valve is found so as to support
                    # graphs where not every valve has a waste.
                    waste_on_valve = get_waste_on_valve(graph, valve)
                    if waste_on_valve:
                        clean_backbone_step.near_waste = waste_on_valve
                    break

            # Find optimum end valve
            for valve in reversed(backbone):
                if (valve in valves_used
                        or valve == clean_backbone_step.solvent_valve):

                    # Need to check if waste on valve is found so as to support
                    # graphs where not every valve has a waste.
                    waste_on_valve = get_waste_on_valve(graph, valve)
                    if waste_on_valve:
                        clean_backbone_step.far_waste = waste_on_valve
                    break
            valves_used = []

        else:
            valves_used.extend(get_valves_used(graph, chempiler, step))

def get_valves_used(
    graph: MultiDiGraph,
    chempiler: Chempiler,
    step: Step
):
    """Get valves used by step."""
    valves_used = []
    if isinstance(step, AbstractBaseStep):

        # Don't include valves used in inert gas transfers
        if step.name == 'CMove':
            from_node = graph.nodes[step.from_vessel]
            if 'chemical' in from_node:
                if from_node['chemical'] in INERT_GAS_SYNONYMS:
                    return []

        # Get valves from locks
        return [
            item
            for item in step.locks(chempiler)[0]
            if graph.nodes[item]['class'] == CHEMPUTER_VALVE
        ]

    # Get valves from nested steps
    else:
        for substep in step.steps:
            valves_used.extend(get_valves_used(graph, chempiler, substep))

    return list(set(valves_used))

def remove_pointless_backbone_cleaning(steps: List[Step]) -> None:
    """Remove pointless CleanBackbone steps.

    Rules are:

    1) No point cleaning between Filter and Dry steps.
    2) No point cleaning between consecutive additions of the same
            reagent.
    """

    # Set counter
    i = len(steps) - 1

    # Iterate whilst counter > 1
    while i > 0:
        # Get the current step
        step = steps[i]

        # CleanBackbone step
        if type(step) in CLEAN_BACKBONE_STEP_TYPES:

            # Get the before and after step
            if i > 0 and i < len(steps) - 1:
                before_step = steps[i - 1]
                after_step = steps[i + 1]

                # Check if it should be removed
                if should_remove_clean_backbone_step(
                    before_step, after_step
                ):
                    # Remove as not needed
                    steps.pop(i)

        # Decrement counter
        i -= 1

def should_remove_clean_backbone_step(
    before_step: Step, after_step: Step
) -> bool:
    """Return True if backbone cleaning is pointless between given two steps.

    Args:
        before_step (Step): Step object of first step of pair.
        after_step (Step): Step object of second step of pair.

    Returns:
        bool: True if backbone cleaning is pointless between given two steps,
            otherwise False.
    """
    # Don't clean between filter and subsequent dry.
    if type(before_step) == Filter and type(after_step) == Dry:
        return True

    else:
        # If adding same thing twice in a row don't clean in between.
        reagents = []
        for other_step in [before_step, after_step]:
            if type(other_step) == Add:
                reagents.append(other_step.reagent)

        if len(reagents) == 2 and len(set(reagents)) == 1:
            return True

    return False

############
# Stirring #
############

def find_stirring_schedule(
    step: Step, stirring: List[str]
) -> List[str]:
    """Find vessels being stirred after given step.

    Args:
        step (Step): step to find stirring changes in.
        stirring (List[str]): List of vessels being stirred before step.

    Returns:
        List[str]: List of vessels being stirred after step.
    """

    # Stir step, add to stirring list
    if type(step) == StartStir:
        stirring.append(step.vessel)

    # StopStip step
    elif type(step) == StopStir:
        # Remove stirring vessel from stirring list
        if step.vessel in stirring:
            stirring.remove(step.vessel)

    # Recursive steps
    elif not isinstance(step, NON_RECURSIVE_ABSTRACT_STEPS):
        # Iterate through substeps
        for substep in step.steps:

            # Get the stirring schedule for the stirring list if Abstract
            if isinstance(substep, AbstractStep):
                find_stirring_schedule(substep, stirring)

            # Repeat above actions
            else:
                if type(substep) == StartStir:
                    stirring.append(substep.vessel)
                elif type(substep) == StopStir:
                    if substep.vessel in stirring:
                        stirring.remove(substep.vessel)

    # Stirring list
    return stirring

def stop_stirring_when_vessels_lose_scope(
    graph_hardware: Hardware,
    steps: List[Step]
) -> None:
    """Add in CStirringControllerStop steps whenever a vessel that is stirring
    becomes empty.
    """

    # Lists to store stirring information
    stirring_schedule = []
    stirred_vessels = []
    insertions = []

    # Find stirring state after every step.
    for i, step in enumerate(steps):
        stirred_vessels = find_stirring_schedule(step, stirred_vessels)
        stirring_schedule.append(stirred_vessels)

    # Look for vessels out of scope that need stirring stopped
    for i, step, vessel_contents, _ in iter_vessel_contents(
            steps, graph_hardware):

        # Iterate through step properties
        for prop, val in step.properties.items():
            # Vessel is present and in stirring schedule, process
            if 'vessel' in prop and val in stirring_schedule[i]:
                if (val in vessel_contents
                        and not vessel_contents[val].reagents):
                    insertions.append((i + 1, StopStir(vessel=val)))

#########
# Other #
#########

def remove_pointless_dry_return_to_rt(steps: List[Step]) -> None:
    """If next step is heating to same temp as dry step, dry step shouldn't
    return to RT at end of stpe.
    """

    # Iterate through all steps
    for i, step in enumerate(steps):

        # Step is a Dry step with temperature set with continue not set
        if type(step) == Dry and step.temp and not step.continue_heatchill:

            # Set continue heatchill if necessary
            if (i + 1 < len(steps)
                    and 'temp' in steps[i + 1].properties
                    and step.temp == steps[i + 1].temp):
                step.continue_heatchill = True

def optimize_separation_steps(steps: List[Step]) -> None:
    """Optimise separation steps to reduce risk of backbone contamination.
    The issue this addresses is that if a product is extracted into the
    aqueous phase, but the organic phase ends up in the backbone, the
    product can redissolve in the organic phase when transferred out of the
    separator.

    Rules implemented here:

    If:
    1) to_vessel of one Separate step is the separation_vessel
    2) Next Separate step uses same kind of solvent (organic or aqueous)

    Then:
    the separation step shouldn't remove the dead volume as you
    run the risk of contaminating the backbone, and there is no need to
    remove the dead volume to risk contaminating the product phase as
    more solvent is going to be added anyway in the next step.

    Args:
        steps (List[Step]): List of steps to optimise separation steps in.
            If not given self._xdl.steps used.
    """

    # Iterate through each step
    for i in range(len(steps)):
        step = steps[i]

        # Step is Separate
        if type(step) == Separate:

            # Waste vessel or destination vessel are the separation vessel
            if (step.waste_phase_to_vessel == step.separation_vessel
                    or step.to_vessel == step.separation_vessel):

                # Increment counter
                j = i + 1
                next_solvent = None

                # Find the next steps
                while j < len(steps):
                    # Next steps are Separate, set the next solvent to this
                    if type(steps[j]) == Separate:
                        next_solvent = steps[j].solvent
                        break
                    j += 1

                # Next solvent is the current solvent, dont
                # remove the dead volume
                if (next_solvent
                    and is_aqueous(next_solvent)
                        == is_aqueous(step.solvent)):
                    step.remove_dead_volume = False

def tidy_up_procedure(
    graph: MultiDiGraph,
    graph_hardware: Hardware,
    chempiler: Chempiler,
    steps: List[Step]
) -> None:
    """Remove steps that are pointless and optimise procedure.
    """

    stop_stirring_when_vessels_lose_scope(graph_hardware, steps)
    remove_pointless_backbone_cleaning(steps)

    # If any CleanBackbone steps
    if any([type(step) == CleanBackbone for step in steps]):
        optimize_backbone_cleaning(graph, chempiler, steps)
