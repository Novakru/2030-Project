from typing import Callable, List, Dict
from networkx import MultiDiGraph

# XDL
from xdl.steps import Step, NON_RECURSIVE_ABSTRACT_STEPS
from xdl.hardware import Hardware

# Relative
from .tracking import iter_vessel_contents, VesselContents
from .constants import (
    CLEAN_VESSEL_BOILING_POINT_FACTOR,
    SOLVENT_BOILING_POINTS,
    TRANSFER_ALL_VOLUME_FACTOR,
    STEPS_PROPERTIES_TO_UPDATE,
)
from ..steps import (
    Filter,
    CleanVessel,
    Transfer,
    CMove,
    Dissolve,
    TakeBackgroundReading,
)
from .utils import property_updater

def add_all_volumes_to_step(
    graph: MultiDiGraph,
    step: Step,
    vessel_contents: Dict[str, VesselContents],
    definite: bool,
    vessels_containing_dissolved_solids: List[str]
):
    """When a volume is given as ``'all'``, two things must be done. First, the
    ``estimated_volume`` prop must be given so that durations can be calculated
    ahead-of-time. Second, if ``volume_tracking_active`` is ``False``, this
    means that runtime volume tracking cannot be used to supply an accurate
    volume, so an explicit volume should be given ``from_vessel['max_volume']``.

    Args:
        step (Step): Step to add volume to
        vessel_contents (dict): Contents of the vessel
        definite (bool): Definite flag from iter_vessel_contents, means that
            volumes in vessel_contents are definitely correct.
        vessels_containing_dissolved_solids: List[str]: List containing any
           vessels that have dissolved solids, at that point in the procedure
           iteration. Used so that runtime volume tracking is not used for
           transferring these solutions as the solid volume is unknown.

    Raises:
        XDLError: Missing desired flask
    """

    # Step is of the Transfer or CMove variety
    if type(step) in [Transfer, CMove]:
        # Volume is the total volume of the container
        if step.volume == 'all':
            step.transfer_all = True

            # Step from vessel is present in vessel contents and volume
            # definitely known
            if definite and step.from_vessel in vessel_contents:
                # Recalculate volume
                step_volume = (
                    vessel_contents[step.from_vessel].volume
                    * TRANSFER_ALL_VOLUME_FACTOR
                )

            # Step from vessel volume unknown, just use max volume
            else:
                step_volume = graph.nodes[step.from_vessel]['max_volume']

            # Only set explicit volume if runtime volume tracking is not active.
            if step.from_vessel in vessels_containing_dissolved_solids:
                step_volume = graph.nodes[step.from_vessel]['max_volume']
                step.volume = step_volume

                # Remove from tracked vessels as it has been emptied.
                while step.from_vessel in vessels_containing_dissolved_solids:
                    vessels_containing_dissolved_solids.remove(step.from_vessel)

            # Set estimated volume for duration estimation.
            step.estimated_volume = step_volume

    # Track vessels containing undissolved solids, as any transfer all from
    # these vessels cannot use runtime volume tracking.
    elif type(step) == Dissolve:
        vessels_containing_dissolved_solids.append(step.vessel)

    # Add all volumes to child steps assume at this point volume tracking can no
    # longer be trusted.
    if hasattr(step, 'children'):
        for child in step.children:
            add_all_volumes_to_step(
                graph,
                child,
                vessel_contents,
                False,
                vessels_containing_dissolved_solids
            )

    # Apply method to substeps of recursive steps
    if not isinstance(step, NON_RECURSIVE_ABSTRACT_STEPS):
        for substep in step.steps:
            add_all_volumes_to_step(
                graph,
                substep,
                vessel_contents,
                definite,
                vessels_containing_dissolved_solids
            )

def add_all_volumes(
    graph: MultiDiGraph,
    graph_hardware: Hardware,
    steps: List[Step],
) -> None:
    """When a volume is given as ``'all'``, two things must be done. First, the
    ``estimated_volume`` prop must be given so that durations can be calculated
    ahead-of-time. Second, if ``volume_tracking_active`` is ``False``, this
    means that runtime volume tracking cannot be used to supply an accurate
    volume, so an explicit volume should be given ``from_vessel['max_volume']``.

    This is the case for ``Dissolve`` steps, as it is uncertain the volume
    added by the solid material.
    """
    prev_vessel_contents = {}

    # Chempiler runtime volume tracking cannot be used after a Dissolve
    # step as there is a risk of underestimating the volume due to the solid
    # not being included in volume tracking. All steps after can use
    # runtime volume tracking as the Dissolve max volume will be carried
    # forward into subsequent transfer all steps.
    vessels_containing_dissolved_solids = []

    # Iterate through the vessel contents
    for _, step, vessel_contents, definite in iter_vessel_contents(
        steps, graph_hardware
    ):
        add_all_volumes_to_step(
            graph,
            step,
            prev_vessel_contents,
            definite,
            vessels_containing_dissolved_solids=vessels_containing_dissolved_solids  # noqa: E501
        )
        prev_vessel_contents = vessel_contents


def add_filter_volumes(
    graph: MultiDiGraph,
    graph_hardware: Hardware,
    steps: List[Step]
) -> None:
    """
    Add volume of filter bottom (aka dead_volume) and volume of material
    added to filter top to Filter steps.
    """
    prev_vessel_contents = {}

    # Iterate through vessel contents
    for _, step, vessel_contents, _ in iter_vessel_contents(
            steps, graph_hardware):

        # Filter step and not using Inline filter
        if type(step) == Filter and not step.properties['inline_filter']:

            # Current filter vessel been seen before
            if step.vessel in prev_vessel_contents:
                # Set the top volume of the Filter step
                step.filter_top_volume = max(prev_vessel_contents[
                    step.vessel].volume, 0)

                # Impossible volume, default to max volume of filter vessel
                if step.filter_top_volume <= 0:
                    step.filter_top_volume = graph.nodes[
                        step.vessel]['max_volume']

            # Not been seen before, set to max volume fo filter vessel
            else:
                step.filter_top_volume = graph.nodes[
                    step.vessel]['max_volume']

            # Need this as setting max_volume reinitialises step and
            # ApplyVacuum internal properties are lost.
            for substep in step.steps:
                substep.on_prepare_for_execution(graph)

        prev_vessel_contents = vessel_contents

def add_clean_vessel_temps(steps: List[Step]) -> None:
    """Add temperatures to CleanVessel steps. Priority is:
    1) Use explicitly given temperature.
    2) If solvent boiling point known use 80% of the boiling point.
    3) Use 30°C.

    Args:
        steps (List[List[Step]]): List of steps to add temperatures to
            CleanVessel steps

    Returns:
        List[List[Step]]: List of steps with temperatures added to
            CleanVessel steps.
    """

    # Iterate through each XDL step
    for step in steps:
        # CleanVessel step
        if type(step) == CleanVessel:
            # Temperature is not set
            if step.temp is None:
                # Obtain the solvent from the step
                solvent = step.solvent.lower()

                # Set the temperature of the step to the solvent's boiling
                # point if present
                if solvent in SOLVENT_BOILING_POINTS:
                    step.temp = (
                        SOLVENT_BOILING_POINTS[solvent]
                        * CLEAN_VESSEL_BOILING_POINT_FACTOR
                    )

                # Default temperature to 30C
                else:
                    step.temp = 30

def assign_background_readings_callback(steps: List[Step]) -> None:
    """Add callback function to background reading steps.

    The callback functions are added in accordance to the future dynamic steps
    with sensors feedback.

    Args:
        steps (List[List[Step]]): List of steps to connect background readings
            steps with corresponding dynamic steps.
    """

    step_to_update: Step = None
    callback: Callable = None
    property_to_update: str = None

    # Traversing the steps list from the last to tht first
    for step in steps[::-1]:
        # Looking for steps to update
        if step.name in STEPS_PROPERTIES_TO_UPDATE:
            step_to_update = step

        if isinstance(step, TakeBackgroundReading):
            # Assigning previously found step_to_update
            # To the found Background reading step
            try:
                property_to_update = STEPS_PROPERTIES_TO_UPDATE[
                    step_to_update.name]
                callback = property_updater(step_to_update, property_to_update)
                step.on_reading = callback
            except AttributeError:
                # If no steps were found to update, just skip
                pass
            # Resetting
            step_to_update = None
