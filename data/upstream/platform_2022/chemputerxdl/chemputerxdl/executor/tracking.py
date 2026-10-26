"""
.. module:: executor.tracking
    :platforms: Unix, Windows
    :synopsis: Functions to track the contents and movements
                of vessel

"""

from typing import List, Dict, Generator, Optional, Tuple
import copy
from xdl.steps import Step, NON_RECURSIVE_ABSTRACT_STEPS
from xdl.hardware import Hardware
from xdl.constants import INERT_GAS_SYNONYMS

from .constants import COMMON_SOLVENT_NAMES
from .errors import XDLNoneVesselError
from .utils import VesselContents
from ..steps import (
    Filter, WashSolid, Dry, Separate, CMove, Evaporate)


# In the sunken city, it lays dreaming...
def iter_vessel_contents(
    steps: List[Step], hardware: Hardware, additions: bool = False
) -> Generator[
        Tuple[
        int,
        Step,
        Dict[str, VesselContents],
        Optional[List[str]],
        bool],
        None, None]:
    """Iterator. Allows you to track vessel contents as they change
    throughout the steps.

    Args:
        steps (List[Step]): List of XDL Steps
        hardware (Hardware): Hardware components in use
        additions (bool, optional): Defaults to False.
            If True, list of what contents were added that step is yielded.

    Yields:
        Tuple: (i, step, contents, {additions})
                i -- Index of step.
                step -- Step object of step.
                contents -- Dict of contents of all vessels after step.
                additions (optional) -- List of contents added during step.
    """

    # Dict to track the vessel contents
    definite = True
    vessel_contents = {}

    # Iterate through all hardware flasks
    for flask in hardware.flasks:
        # Get the contents of each vessel
        vessel_contents[flask.id] = VesselContents(
            [flask.chemical], flask.current_volume
        )

    # Enumerate through all XDL steps
    for i, step in enumerate(steps):
        # List for keeping track of any new additions to any vessel contents
        additions_l = []

        # Dealing with Separate step
        if type(step) == Separate:
            definite = False
            # Add vessels to additions if solvent present
            if step.solvent:
                additions_l.append(step.solvent)

            # Iterate through each vessel in the current step
            for prop in [
                'from_vessel',
                'to_vessel',
                'waste_phase_to_vessel_to_use'
            ]:
                vessel = step.properties[prop]
                # Set default contents if not already present
                if vessel is None:
                    raise XDLNoneVesselError(step, prop)
                vessel_contents.setdefault(
                    vessel,
                    VesselContents([], hardware[vessel].current_volume)
                )

            # Empty from_vessel
            from_reagents = vessel_contents[step.from_vessel].reagents
            from_volume = vessel_contents[step.from_vessel].volume
            vessel_contents[step.from_vessel].reagents = []
            vessel_contents[step.from_vessel].volume = 0

            # Add from_vessel contents to to_vessel and
            # waste_phase_to_vessel
            vessel_contents[step.to_vessel].reagents.extend(from_reagents)
            vessel_contents[step.waste_phase_to_vessel_to_use].reagents.extend(
                from_reagents
            )

            # Solvent is present in the step, determine purpose and
            # track appropriate contents
            if step.solvent:
                # Solvent used for extraction
                if step.purpose == 'extract':
                    # Add solvent to the to_vessel
                    vessel_contents[step.to_vessel].reagents.append(
                        step.solvent
                    )

                    # Add volume of solvent to to_vessel
                    vessel_contents[step.to_vessel].volume +=\
                        step.solvent_volume * step.repeats

                    # Add from_vessel volume to waste_phase_to_vessel
                    vessel_contents[
                        step.waste_phase_to_vessel_to_use].volume += from_volume

                # Solvent used for wash
                elif step.purpose == 'wash':
                    # Add the solvent to waste_phase_to_vessel
                    vessel_contents[step.waste_phase_to_vessel_to_use]\
                        .reagents.append(step.solvent)

                    # Add volume of solvent to waste_phase_to_vessel
                    vessel_contents[step.waste_phase_to_vessel_to_use]\
                        .volume += step.solvent_volume * step.repeats

                    # Add from_vessel volume to the to_vessel
                    vessel_contents[step.to_vessel].volume += from_volume

        # Dealing with Filter step
        elif type(step) == Filter:
            definite = False

            # Iterate through each vessel in the step
            for vessel in [step.vessel, step.waste_vessel]:
                # Set default contents if not already set
                vessel_contents.setdefault(
                    vessel,
                    VesselContents([], hardware[vessel].current_volume)
                )

            # Get filter reagents and volumes
            filter_reagents = vessel_contents[step.vessel].reagents
            filter_volume = vessel_contents[step.vessel].volume

            # Empty the vessel contents
            vessel_contents[step.vessel].reagents = []
            vessel_contents[step.vessel].volume = 0

            # Move contents to waste vessel
            vessel_contents[step.waste_vessel].reagents.extend(
                filter_reagents
            )
            vessel_contents[step.waste_vessel].volume += filter_volume

        # Dealing with WashSOlid step
        elif type(step) == WashSolid:
            definite = False

            # Iterate through step vessels and set default contents
            for vessel in [step.vessel, step.waste_vessel]:
                vessel_contents.setdefault(
                    vessel,
                    VesselContents([], hardware[vessel].current_volume)
                )

            # Get vessel contents
            reagents = vessel_contents[step.vessel].reagents
            volume = vessel_contents[step.vessel].volume

            # Empty vessel contents
            vessel_contents[step.vessel].reagents = []
            vessel_contents[step.vessel].volume = 0

            # Move contents to waste vessel
            vessel_contents[step.waste_vessel].reagents.extend(reagents)
            vessel_contents[step.waste_vessel].volume += volume

            # Add solvent addition
            additions_l.append(step.solvent)

        # Dealing with Dry step
        elif type(step) == Dry:
            definite = False
            # This is necessary to stop move command putting filter into
            # negative volume
            vessel_contents.setdefault(
                step.vessel,
                VesselContents([], hardware[step.vessel].current_volume)
            )
            vessel_contents[step.vessel].volume = 0

        # Dealing with Evaporate step
        elif type(step) == Evaporate:
            definite = False

            # Rotavap is present in vessel contents
            if step.vessel in vessel_contents:

                # Iterate through all rotavap reagents/solvents
                for j in reversed(
                    range(len(vessel_contents[step.vessel].reagents))
                ):
                    # Get current reagent
                    reagent = vessel_contents[step.vessel].reagents[j]

                    # Remove all common solvents during evaporation
                    if reagent.lower() in COMMON_SOLVENT_NAMES:
                        vessel_contents[step.vessel].reagents.pop(j)

                # Set rotavap volume to 0
                vessel_contents[step.vessel].volume = 0

            # No rotavap, create empty contents
            else:
                vessel_contents[step.vessel] = VesselContents([], 0)

        # Handle normal Move steps.
        else:
            # Iterate through vessels and volume in movement steps
            for from_vessel, to_vessel, volume in get_movements(step):
                empty_from_vessel = False

                # Add vessels to vessel_contents if they aren't there.
                if ('chemical' in hardware[from_vessel].properties
                        and hardware[from_vessel].chemical
                        in INERT_GAS_SYNONYMS):
                    continue

                # Set default contents for to and from vessel
                for vessel in [from_vessel, to_vessel]:
                    vessel_contents.setdefault(
                        vessel,
                        VesselContents([], hardware[vessel].current_volume))

                # Get actual volume if volume is 'all'
                if volume == 'all':
                    volume = vessel_contents[from_vessel].volume
                    empty_from_vessel = True

                # Add volume to to_vessel and additions list
                vessel_contents[to_vessel].volume += volume
                vessel_contents[to_vessel].reagents.extend(
                    vessel_contents[from_vessel].reagents
                )
                additions_l.extend(vessel_contents[from_vessel].reagents)

                # Remove volume from from_vessel.
                vessel_contents[from_vessel].volume -= volume

                # Flasks should be treated as bottomless, i.e. even if they
                # hit negative volume they should still contain their
                # reagent.
                if (vessel_contents[from_vessel].volume <= 0
                    and from_vessel not in [
                        item.id for item in hardware.flasks
                ]):
                    vessel_contents[from_vessel].reagents = []
                    vessel_contents[from_vessel].volume = 0

                # Extend list of reagents added in the step.
                # Empty from_vessel if 'all' volume specified.
                if empty_from_vessel:
                    vessel_contents[from_vessel].volume = 0
                    vessel_contents[from_vessel].reagents = []

        # Yield the current position, step, vessel contents, and new
        # additions if new additions were added
        if additions:
            yield (
                i,
                step,
                copy.deepcopy(vessel_contents),
                copy.deepcopy(additions_l),
                definite,
            )

        # Yield the position, step, and vessel contents if no new additions
        else:
            yield (i, step, copy.deepcopy(vessel_contents), definite)

def get_movements(step: Step) -> List[Tuple[str, str, float]]:
    """Get all liquid movements associated with given step. Works recursively
    going down step tree until a CMove step is encountered and then the
    liquid movement from the CMove step is added to the movements list.

    Args:
        step (Step): Step to get liquid movements from.

    Returns:
        List[Tuple]: List of tuples (from_vessel, to_vessel, volume)
    """

    movements = []

    # All movements are obtained from CMove.
    if type(step) == CMove:
        movements.append((step.from_vessel, step.to_vessel, step.volume))

    # Recursive calls until CMove steps encountered.
    elif not isinstance(step, NON_RECURSIVE_ABSTRACT_STEPS) and step.steps:
        for sub_step in step.steps:
            movements.extend(get_movements(sub_step))

    return movements
