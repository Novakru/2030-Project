from typing import List
from networkx import MultiDiGraph

# XDL
from xdl.steps import Step, NON_RECURSIVE_ABSTRACT_STEPS
from xdl.reagents import Reagent

# Relative
from ..steps import (
    SetStirRate,
    CMove,
    Add,
    StartStir,
    StopStir,
    StartHeatChill,
    StopHeatChill,
    Shutdown
)
from ..constants import DEFAULT_STIR_SPEED, DEFAULT_STIR_REAGENT_FLASK_SPEED
from ..utils.execution import graph_flasks

###################
# Set Stir Speeds #
###################

def set_all_stir_speeds(steps: List[Step]) -> None:
    """Set stir RPM to default at start of procedure for all stirrers
    used in procedure.
    """

    # List for stirring vessels
    stir_vessels = []

    # Iterate through steps and get stirring vessels
    for step in steps:
        stir_vessels.extend(get_stir_vessels(step))

    # Add CSetStirRate step for each vessel
    for vessel in sorted(list(set(stir_vessels))):
        steps.insert(0, SetStirRate(vessel, DEFAULT_STIR_SPEED))

def get_stir_vessels(step: Step):
    """Get vessels being stirred using CStirringControllerStart in substeps of
    given step.

    Args:
        step (Step): Step to find vessels being stirred.

    Returns:
        List[str]: List of vessels being stirred in given step.
    """

    # List to hold stirring vessels
    stir_vessels = []

    # Get through child steps if present
    if 'children' in step.properties:
        for child in step.children:
            stir_vessels.extend(get_stir_vessels(child))

    # Non recursive step, add to stirring list if of type StartStir
    if isinstance(step, NON_RECURSIVE_ABSTRACT_STEPS):
        if type(step) == StartStir:
            stir_vessels.append(step.vessel)

    # Recursive steps
    else:
        # Iterate through each substep of the current step
        for substep in step.steps:
            stir_vessels.extend(get_stir_vessels(substep))

    # Return stirring vessels
    return stir_vessels

#############################
# Reagent Special Treatment #
#############################

def add_reagent_last_minute_addition_steps(
    graph: MultiDiGraph, steps: List[Step], reagents: List[Reagent]
) -> None:
    """Add addition steps where reagent specify that something must be added
    to them just before use with last_minute_addition property.
    """

    # Iterate through each reagent defined in XDL
    for reagent in reagents:
        # Exract addition and volume from reagent
        addition, volume = (
            reagent.last_minute_addition,
            reagent.last_minute_addition_volume
        )

        # Both are present
        if addition and volume:
            reagent_flask = None
            # Iterate through each flask in the Chemputer graph
            for flask, data in graph_flasks(graph, data=True):
                # Set reagent flask if the graph flask chemical matches
                # the Reagent ID
                if data['chemical'] == reagent.name:
                    reagent_flask = flask
                    break

            # Reagent flask was found
            if reagent_flask:
                first_use = -1

                # Iterate through each XDL step
                for i, step in enumerate(steps):
                    # Get the Base steps from the current step
                    base_steps = step.base_steps

                    # Iterate through each base step
                    for base_step in base_steps:
                        # Assign first use if flask is used in CMove
                        if (type(base_step) == CMove
                                and base_step.from_vessel == reagent_flask):
                            first_use = i
                            break

                    # First use been assigned, break out
                    if first_use >= 0:
                        break

                # Insert Add step if first use been assigned
                if first_use >= 0:
                    steps.insert(
                        first_use,
                        Add(vessel=reagent_flask,
                            reagent=addition,
                            volume=volume))

def add_reagent_storage_steps(
    graph: MultiDiGraph, steps: List[Step], reagents: List[Reagent]
) -> None:
    """Add stirring and heating steps at start and end to flasks where
    reagent has stirring or temperature control specified in Reagents
    section of XDL.
    """

    # Iterate through each reagent defined in the XDL
    for reagent in reagents:
        # Stirring or heating is present
        if reagent.stir or reagent.temp:
            reagent_flask = None

            # Iterate through each flask defined in the Chemputer graph
            for flask, data in graph_flasks(graph, data=True):
                # Set reagent flask if the graph flask chemical matches
                # the Reagent ID
                if data['chemical'] == reagent.name:
                    reagent_flask = flask
                    break

            # The reagent flask was found and assigned from the graph
            if reagent_flask:
                # Add StartStir and StopStir steps if reagent is stir
                if reagent.stir:
                    steps.insert(
                        0,
                        StartStir(
                            vessel=reagent_flask,
                            stir_speed=DEFAULT_STIR_REAGENT_FLASK_SPEED
                        )
                    )

                    steps.append(StopStir(vessel=reagent_flask))

                # Reagent temperature is defined
                # Add StartHeat and StopHeat steps
                if reagent.temp is not None:
                    steps.insert(
                        0,
                        StartHeatChill(vessel=reagent_flask,
                                       temp=reagent.temp),
                    )
                    steps.append(
                        StopHeatChill(
                            vessel=reagent_flask,
                        ))

#########
# Other #
#########

def add_in_final_shutdown(steps: List[Step]):
    """Add Shutdown step to the end of the XDL steps.
    Final step to ensure any hardware is gracefully shutdown.
    """
    steps.append(Shutdown())
