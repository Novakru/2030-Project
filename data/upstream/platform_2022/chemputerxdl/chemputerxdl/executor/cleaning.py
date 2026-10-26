"""
.. module:: executor.cleaning
    :platforms: Windows, Unix
    :synopsis: Orchestrates Cleaning steps. Moves them to appropriate places,
                adds necessary steps, picks best solvents etc.

"""

from typing import List, Tuple, Dict
import re
import time
import copy
from .constants import (
    COMMON_SOLVENT_NAMES,
    SOLVENT_CONTAINING_STEPS,
    GENERIC_ORGANIC,
    CLEANING_SOLVENT_BLACKLIST,
    CLEAN_BACKBONE_AFTER_STEPS,
    CLEANING_SOLVENT_PREFER_NOT_TO_USE,
    SOLVENT_BOILING_POINTS,
    CLEAN_VESSEL_BOILING_POINT_FACTOR,
    NO_DUPLICATE_CLEAN_STEPS,
    COMMON_BASES
)
from .tracking import iter_vessel_contents, VesselContents
from ..steps import Step, Add, Separate, Dissolve, CleanVessel, CleanBackbone
from xdl.hardware import Hardware
from xdl.reagents import Reagent
from xdl.errors import XDLError
from xdl.constants import AQUEOUS_KEYWORDS
from xdl.utils.logging import get_logger

if False:  # For type annotations
    from xdl.xdl import XDL

"""
Backbone Cleaning Rules
-----------------------
If a step contains a common solvent then that solvent is used for backbone
cleaning after that step. If the last clean didn't also use that solvent, a
backbone clean using the solvent is also performed before the step. If no
common solvent is used in a step the last encountered common solvent is used.
e.g.
Add( acetone )
CleanBackbone( acetone )
Add( acetic anhydride )
CleanBackbone( acetone )
CleanBackbone( water )
Add( aqueous_oxone_solution )
CleanBackbone( water )
CleanBackbone( ether )
Add( ether )
CleanBackbone( ether )
...

Vessel Cleaning Rules
---------------------
Vessels are cleaned after emptying steps if the step preceding the emptying step
was a dissolve step. This is to make sure that no vessels are cleaned after
emptying steps when they actually still contain solids.
e.g.
...
Evaporate rotavap
Dissolve rotavap
Transfer rotavap -> reactor
CleanVessel rotavap
...

"""

def get_available_solvents(xdl_obj: 'XDL') -> List[str]:
    """Get list of common available solvents in XDL object.
    Reagents list and graph are searched for available solvents.

    Args:
        reagents (XDL): XDL object to get available solvents from.

    Returns:
        List[str]: List of common solvents contained in reagents.
    """
    solvents = []
    reagents = [
        reagent.name for reagent in xdl_obj.reagents if not reagent.preserve]

    graph_hardware = xdl_obj.executor._graph_hardware
    reagents.extend([flask.chemical for flask in graph_hardware.flasks])

    reagents = sorted(list(set(reagents)))
    for reagent in reagents:
        if 'solution' not in reagent.lower():
            for solvent in COMMON_SOLVENT_NAMES:
                if solvent == reagent.lower():

                    # Don't want to use solvents that damage parts of Chemputer.
                    if not reagent.lower() in CLEANING_SOLVENT_BLACKLIST:
                        solvents.append(reagent)

    # add reagents used for cleaning to solvents
    solvents.extend([
        reagent.name
        for reagent in xdl_obj.reagents
        if reagent.use_for_cleaning])

    # This is to remove preserved solvents from the cleaning routines
    # as they may be expensive
    preserved_solvents = []
    for solvent in solvents:
        for reagent in xdl_obj.reagents:
            if reagent.name == solvent and reagent.preserve:
                preserved_solvents.append(solvent)

    # Remove the solvents from the list
    solvents = [
        solvent for solvent in solvents
        if solvent not in preserved_solvents]

    return sorted(list(set(solvents)))

def get_cleaning_schedule(
    xdl_obj: 'XDL'
) -> List[str]:
    """Get list of what solvent should be used to clean at every step.

    Args:
        xdl_obj (XDL): XDL object to get cleaning schedule for.
    Returns:
        List[str]: List of organic cleaning solvents to use with every step.
            Solvents are selected for every step regardless of whether an
            organic clean should be performed at that step.
    """
    available_solvents = get_available_solvents(xdl_obj)
    if not available_solvents:
        return (None, None)
    schedule = [None for step in xdl_obj.steps]
    base_schedule = copy.deepcopy(schedule)

    # get solvent addition steps, sorted by step index
    solvent_additions = get_solvent_additions(xdl_obj)

    for j, solvent_addition in enumerate(solvent_additions):
        bases = []
        for reagent in solvent_addition[1]:
            cleaning_solvent = get_reagent_cleaning_solvent(
                reagent_name=reagent,
                xdl_reagents=xdl_obj.reagents,
                available_solvents=available_solvents)
            if cleaning_solvent is not None:
                schedule[j] = cleaning_solvent
            if reagent in [
                    xdl_reagent.name for xdl_reagent in xdl_obj.reagents]:
                reagent_props = [
                    xdl_reagent for xdl_reagent in xdl_obj.reagents
                    if xdl_reagent.name == reagent][0]
                if (reagent_props.role == 'base'
                        or reagent_props.name in COMMON_BASES):
                    bases.append(reagent)
        if bases:
            base_schedule[j] = 1

    # Fill in blanks in schedule.
    # 1) Add organic solvents to steps that add a solvent blacklisted for
    # cleaning.
    organic_solvents = [(i, item)
                        for i, item in enumerate(schedule)
                        if item and 'water' not in item]
    for i in range(len(schedule)):
        if schedule[i] == GENERIC_ORGANIC:
            if organic_solvents:
                # Get closest organic solvent in schedule
                schedule[i] = sorted(
                    organic_solvents, key=lambda x: abs(x[0] - i))[0][1]
            else:
                # Choose random organic solvent.
                for solvent in available_solvents:
                    if 'water' not in solvent:
                        schedule[i] = solvent

    # 2) Treat consecutive SOLVENT_CONTAINING_STEPS as groups and if one step in
    #    group has a solvent apply that to all steps in the group.
    i = 0
    while i < len(schedule):
        reagent = schedule[i]
        j = i
        if reagent:
            while (
                j >= 0
                and type(xdl_obj.steps[j]) in SOLVENT_CONTAINING_STEPS
                and not schedule[j]
            ):
                j -= 1
                schedule[j] = reagent
            j = i
            while (
                j < len(xdl_obj.steps)
                and type(xdl_obj.steps[j]) in SOLVENT_CONTAINING_STEPS
                and not schedule[j]
            ):
                j += 1
                schedule[j] = reagent
        i = max(j, i + 1)

    # 3) Go forward applying last encountered solvent to every step in schedule.
    try:
        current_reagent = [item for item in schedule if item][0]
    except IndexError:
        current_reagent = available_solvents[0]
    for i, reagent in enumerate(schedule):
        if reagent:
            if 'water' not in reagent:
                current_reagent = reagent
        else:
            schedule[i] = current_reagent

    return (schedule, base_schedule)

def get_reagent_cleaning_solvent(
    reagent_name: str, xdl_reagents: List[Reagent], available_solvents
) -> bool:
    """Return True if reagent_name is an aqueous reagent, otherwise False.

    Args:
        reagent_name (str): Name of reagent.

    Returns:
        bool: True if reagent_name is aqueous, otherwise False.
    """
    # See if any of available solvents are added.
    if reagent_name in available_solvents:
        return reagent_name

    # Look for stuff like 'X in THF'
    for solvent in available_solvents:
        if re.match(r'(?:[ _]|^)' + solvent + r'(?:[ _]|$)', reagent_name):
            return solvent

    for xdl_reagent in xdl_reagents:
        if xdl_reagent.name == reagent_name and xdl_reagent.clean_with:
            if xdl_reagent.clean_with in available_solvents:
                return xdl_reagent.clean_with

    for word in AQUEOUS_KEYWORDS:
        if word in reagent_name:
            if 'water' in available_solvents:
                return 'water'
            else:
                for solvent in available_solvents:
                    if ' water' in solvent:
                        return solvent

    if reagent_name in CLEANING_SOLVENT_BLACKLIST:
        return GENERIC_ORGANIC
    return None

def get_clean_backbone_steps(steps: List[Step]) -> List[int]:
    """Get list of steps after which backbone should be cleaned.

    Returns:
        List[int]: List of indexes for steps after which the backbone should
            be cleaned.
    """
    clean_backbone_steps = []
    for i, step in enumerate(steps):
        should_clean_backbone = type(step) in CLEAN_BACKBONE_AFTER_STEPS

        # Check if child steps require backbone cleaning.
        if (not should_clean_backbone
            and hasattr(step, 'children')
                and step.children):
            for child_step in step.steps:
                if type(child_step) in CLEAN_BACKBONE_AFTER_STEPS:
                    should_clean_backbone = True

        if should_clean_backbone:
            # Don't clean after solid additions
            if not (type(step) == Add and step.volume is None):
                clean_backbone_steps.append(i)
    return clean_backbone_steps

def get_clean_backbone_sequence(xdl_obj) -> List[Tuple[int, str]]:
    """Get sequence of backbone cleans required. Cleans are given as tuples like
    this (step_index, cleaning_solvent).

    Returns:
        List[int, str]: List of Tuples like this
            [(step_to_insert_backbone_clean, cleaning_solvent)...]
    """
    # get list of solvents at each step, with the last element of the list
    # specifying indices of steps with basic reagents / solvents.
    step_solvents = get_cleaning_schedule(
        xdl_obj=xdl_obj)
    if len(step_solvents) > 1:

        # base_reagent_steps specified in final element of step_solvents as
        # ['basic_reagent_steps', i...] where i = step index.
        base_reagent_steps = step_solvents[1]
        step_solvents = step_solvents[0]
    else:
        step_solvents, base_reagent_steps = [], []

    # get list of step indices for steps requiring a backbone clean.
    clean_backbone_steps = get_clean_backbone_steps(xdl_obj.steps)

    # get list of step indices and cleaning solvents corresponding to backbone
    # cleans to be inserted into xdl object steps; and also list of step
    # indices for those backbone cleans to be inserted after addition of basic
    # reagents. Basic reagents require more thorough cleaning, so this will be
    # used to insert extra cleaning steps.
    cleans, base_cleans = [], []

    for i, step_i in enumerate(clean_backbone_steps):

        # Get after_type and before_type
        after_solvent = None
        if base_reagent_steps[step_i]:
            base_cleans.append(step_i + 1)
        if i + 1 < len(clean_backbone_steps):
            next_step_i = clean_backbone_steps[i + 1]
            if next_step_i < len(step_solvents):
                after_solvent = step_solvents[next_step_i]

        before_solvent = step_solvents[step_i]

        # If on last clean backbone step then there will be no after solvent.
        if not after_solvent:
            after_solvent = before_solvent
        if before_solvent == after_solvent:
            cleans.append((step_i + 1, before_solvent))
        elif before_solvent != after_solvent:
            cleans.append((step_i + 1, before_solvent))
            cleans.append((step_i + 1, after_solvent))
    return cleans, base_cleans

def add_cleaning_steps(xdl_obj: 'XDL') -> 'XDL':
    """Add cleaning steps to XDL object with appropriate cleaning solvents.

    Args:
       xdl_obj (XDL): XDL object to add cleaning steps to.

    Returns:
        XDL: xdl_obj with cleaning steps added.
    """

    # get list of backbone cleaning steps, as well as list of step indices
    # for backbone cleaning steps that occur after addition of a base. This is
    # to ensure an extra clean is inserted after addition of bases.
    clean_backbone_sequence, base_cleans = get_clean_backbone_sequence(
        xdl_obj=xdl_obj)

    if clean_backbone_sequence:
        for i, solvent in reversed(clean_backbone_sequence):

            # If organic_cleaning_solvent is given use it otherwise use solvent
            # in synthesis.
            if ('water' not in solvent
                    and xdl_obj.executor._organic_cleaning_solvent):
                solvent = xdl_obj.executor._organic_cleaning_solvent
            if i - 1 >= 0:
                prev_step = xdl_obj.steps[i - 1]
                clean = True
                # Don't clean certain steps if the solvent used for cleaning
                # is the same as the solvent being added.
                for step_type in NO_DUPLICATE_CLEAN_STEPS:
                    if type(prev_step) == step_type:
                        for item in ['reagent', 'solvent']:
                            if item in prev_step.properties:
                                if prev_step.properties[item] == solvent:
                                    clean = False
                if not clean:
                    continue

            # Insert a backbone clean with appropriate solvent.
            xdl_obj.steps.insert(i, CleanBackbone(solvent=solvent))

            # If this cleaning step is after addition of a base, insert an
            # extra backbone clean as basic reagents require more thorough
            # cleaning.
            if base_cleans and i in base_cleans:
                xdl_obj.steps.insert(i, CleanBackbone(solvent=solvent))
        xdl_obj = add_cleaning_steps_at_beginning_and_end(xdl_obj)

    # do final check to make sure that incompatible reagents are not mixed
    # in backbone. Add extra cleaning steps and / or change cleaning solvents
    # if necessary to prevent this
    # DEPRECATED: reagent.incompatible_reagents is not part of the new XDL
    # standard. Eventually this code should be removed. Keeping here for now for
    # legacy.
    # xdl_obj = final_safety_check_incompatible_reagents(xdl_obj)

    return xdl_obj

def add_cleaning_steps_at_beginning_and_end(xdl_obj: 'XDL') -> 'XDL':
    """Add CleanBackbone steps at beginning and end of procedure with
    appropriate solvents.

    Args:
        xdl_obj (XDL): XDL object to add CleanBackbone steps to.

    Returns:
        XDL: xdl_obj with CleanBackbone steps added at beginning and end with
            appropriate solvents.
    """
    # Set default solvents to use if nothing better found.
    available_solvents = get_available_solvents(xdl_obj)
    start_solvent, end_solvent = None, None
    if len(available_solvents) > 0:
        start_solvent, end_solvent = (
            available_solvents[0], available_solvents[0])
    cleaning_solvents = [
        step.reagent
        for step in xdl_obj.steps
        if type(step) == Add and step.reagent in available_solvents
    ]
    # Set start solvent and end solvent to first used and last used cleaning
    # solvent if they exist.
    if len(cleaning_solvents) > 0:
        start_solvent = cleaning_solvents[0]
        end_solvent = cleaning_solvents[-1]
    # If end solvent is in blacklist look for a better solvent in available
    # solvents.
    if end_solvent in CLEANING_SOLVENT_PREFER_NOT_TO_USE:
        # Do it like this as probably prefer to use solvent from procedure
        # rather than random one available.
        potential_solvents = cleaning_solvents + available_solvents
        for solvent in potential_solvents:
            if solvent not in CLEANING_SOLVENT_PREFER_NOT_TO_USE:
                end_solvent = solvent
                break
    # Add cleaning steps.
    if start_solvent:
        xdl_obj.steps.insert(0, CleanBackbone(solvent=start_solvent))
    else:
        xdl_obj.steps.append(CleanBackbone(solvent=end_solvent))
    return xdl_obj

def get_solvent_additions(xdl_obj):
    """
    Calls _iter_vessel_contents to get list of step indices and associated
    solvent additions

    Args:
        xdl_obj (XDL): XDL object

    Returns:
        List[list]: list of [i, List[str]] where i = step index in xdl_obj.steps
            and List[str] = list of reagent ids for solvents added in that step
    """
    # get solvent addition steps, sorted by step index
    solvent_additions = [
        [i, additions]
        for i, _, _, additions, _ in iter_vessel_contents(
            xdl_obj.steps, xdl_obj.executor._graph_hardware, additions=True)]
    return sorted(
        solvent_additions, key=lambda x: x[0])

def final_safety_check_incompatible_reagents(xdl_obj):
    """
    Checks that reagents which are potentially incompatible with solvents that
    would otherwise be used for cleaning to come into contact with these
    solvents. This is done by changing cleaning solvents used where possible;
    if this is not possible (i.e. due to other reagents having specific cleaning
    solvents) additional cleaning steps are inserted using a compatible solvent

    Args:
        xdl_obj (XDL): XDL object
    Raises:
        XDLError: If a reagent is incompatible with all available cleaning
            solvents, user should add an additional cleaning solvent that is
            compatible
    Returns:
        xdl_obj (XDL): modified XDL object with backbone cleaning steps adjusted
    """

    # check if any reagents can potentially clash; if not, no need to change
    # cleaning steps
    incompatible_reagents = {}
    for xdl_reagent in xdl_obj.reagents:
        if xdl_reagent.incompatible_reagents:
            incompatible_reagents.update(
                {xdl_reagent.name: xdl_reagent.incompatible_reagents})
    if not incompatible_reagents:
        return xdl_obj

    # keep track of any reagents that have fixed post-cleaning solvents
    # in case these cleaning solvents are incompatible with another reagent
    fixed_cleaning_solvents = {
        xdl_reagent.name: xdl_reagent.clean_with
        for xdl_reagent in xdl_obj.reagents
        if xdl_reagent.clean_with}

    # get steps that affect what reagents are present in backbone - addition
    # steps and cleans
    reagent_steps = [
        step for step in get_solvent_additions(xdl_obj)
        if step[1]]
    clean_steps = [
        [j, step.solvent] for j, step in enumerate(xdl_obj.steps)
        if type(step) == CleanBackbone]

    # init list to keep track of extra cleans required to ensure incompatible
    # cleaning solvents are separated by an additional backbone clean with a
    # safe solvent
    extra_safety_cleans = []

    # iterate through non-backbone cleaning solvent addition steps, find and fix
    # any potential safety clashes and work out extra safety cleans required
    for j, reagent_step in enumerate(reagent_steps):
        solvent_clashes = []
        for reagent in reagent_step[1]:
            if reagent in incompatible_reagents:
                solvent_clashes.extend(incompatible_reagents[reagent])
        if solvent_clashes:

            # check the solvents scheduled to be used for cleaning immediately
            # before and immediately after this step, as these may be
            # incompatible
            next_clean = [
                clean for clean in clean_steps
                if clean[0] > reagent_step[0]][0]
            previous_clean = [
                clean for clean in clean_steps
                if clean[0] < reagent_step[0]][-1]

            # check potential cleaning solvents; if none are compatible with
            # one or more reagent, raise a XDL error as this may be unsafe
            available_solvents = [
                solvent for solvent in get_available_solvents(xdl_obj)
                if solvent not in solvent_clashes]
            if not available_solvents:
                raise XDLError(
                    f'there are no cleaning solvents compatible\n'
                    f'with one or more of the following: {reagent_step[1]}')

            # if next or previous solvent are incompatible, change them to
            # a solvent that is compatible with reagent(s)
            if next_clean[1] in solvent_clashes:
                xdl_obj.steps[next_clean[0]].solvent = available_solvents[0]
            if previous_clean[1] in solvent_clashes:
                if j > 0:

                    # if incompatible solvent from the previous clean is
                    # required as a post-cleaning solvent for another reagent,
                    # solve this by adding an additional cleaning step using
                    # a compatible solvent
                    for previous_addition in list(set(reagent_steps[j - 1][1])):
                        if previous_addition in fixed_cleaning_solvents:
                            if previous_clean[1] == fixed_cleaning_solvents[
                                    previous_addition]:
                                extra_safety_cleans.append(
                                    [j + 1, previous_clean[1]])

                xdl_obj.steps[previous_clean[0]].solvent = available_solvents[0]

    # if additional cleaning steps are required to prevent incompatible reagents
    # coming into contact, insert them here
    if extra_safety_cleans:
        for i, solvent in reversed(extra_safety_cleans):
            xdl_obj.steps.insert(i, CleanBackbone(solvent=solvent))
    return xdl_obj

###################
# Vessel Cleaning #
###################

def get_vessel_emptying_steps(
    steps: List[Step], hardware: Hardware
) -> List[Tuple[int, str, Dict[str, VesselContents]]]:
    """Get steps at which a filter vessel is emptied. Also return full
    list of vessel contents dict at every step.

    Returns:
        List[Tuple[int, str, Dict[str, VesselContents]]]: List of tuples,
            format: [(step_index,
                      filter_vessel_name,
                      {vessel: VesselContents, ...})...]
    """
    vessel_emptying_steps = []
    full_vessel_contents = []
    prev_vessel_contents = {}
    for i, _, vessel_contents, _ in iter_vessel_contents(steps, hardware):
        full_vessel_contents.append(vessel_contents)
        for vessel, contents in vessel_contents.items():
            # If target vessel has just been emptied, append to vessel
            # emptying steps.
            if vessel in prev_vessel_contents:
                if (not contents.reagents
                        and prev_vessel_contents[vessel].reagents):
                    vessel_emptying_steps.append((i, vessel))

        prev_vessel_contents = vessel_contents
    return vessel_emptying_steps

def get_clean_vessel_sequence(
    xdl_obj: 'XDL', hardware: Hardware
) -> List[Tuple[int, str, str]]:
    """Get list of places where CleanVessel steps need to be added along with
    vessel name and solvent to use.

    Args:
        xdl_obj (XDL): XDL object to get vessel cleaning sequence for.
        hardware (Hardware): Hardware to use when finding emptying steps.

    Returns:
        List[Tuple[int, str, str]]: List of tuples like below.
            [(index_to_insert_clean_vessel_step, vessel, solvent_to_use)...]
    """
    # Get all solvents available for cleaning.
    available_solvents = get_available_solvents(xdl_obj)
    steps = xdl_obj.steps
    cleaning_sequence = []
    prev_vessel_contents = {}
    # Go through and find conditions where CleanVessel steps should be added.
    # Find solvents to clean with as well.
    for i, step, vessel_contents, _ in iter_vessel_contents(steps, hardware):
        cleaning_solvents = []
        # Clean separation from_vessel
        if (type(step) == Separate
            and step.from_vessel not in [
                step.separation_vessel,
                step.to_vessel,
                step.waste_phase_to_vessel]):
            cleaning_solvents = get_clean_vessel_solvents(xdl_obj,
                                                          step.from_vessel,
                                                          prev_vessel_contents,
                                                          available_solvents)
        # Clean if vessel is empty the step after a dissolve step. This rule is
        # used as it guarantees that any solid is also gone from the vessel.
        elif (i > 0 and type(steps[i - 1]) == Dissolve
              and not vessel_contents[steps[i - 1].vessel].reagents):
            cleaning_solvents = get_clean_vessel_solvents(xdl_obj,
                                                          steps[i - 1].vessel,
                                                          prev_vessel_contents,
                                                          available_solvents)
        # For all cleaning solvents found add them to the sequence along with
        # the vessel and position in procedure.
        for cleaning_solvent in list(set(cleaning_solvents)):
            cleaning_sequence.append((
                i + 1, step.from_vessel, cleaning_solvent))
        prev_vessel_contents = vessel_contents
    return cleaning_sequence

def get_clean_vessel_solvents(
    xdl_obj: 'XDL',
    vessel: str,
    prev_vessel_contents: Dict[str, VesselContents],
    available_solvents: List[str]
) -> List[str]:
    """Given empty vessel name and previous step vessel contents find what
    solvents should be used to clean the vessel.

    Args:
        xdl_obj (XDL): XDL object. Needed to access reagents list and check if
            any reagents have a specified cleaning reagent.
        vessel (str): Vessel to be cleaned.
        prev_vessel_contents (Dict[str, VesselContents]): All vessel contents at
            step before vessel is emptied and should be cleaned.
        available_solvents (List[str]): Solvents available for cleaning the
            vessel.

    Returns:
        List[str]: List of solvents that the vessel should be cleaned with.
    """
    solvents = []
    # Only clean vessel if it has had previous contents.
    if vessel in prev_vessel_contents:
        # Get all cleaning solvents associated with reagents that were in
        # vessel.
        cleaning_solvents = [
            get_reagent_cleaning_solvent(
                reagent, xdl_obj.reagents, available_solvents)
            for reagent in prev_vessel_contents[vessel]
        ]
        for cleaning_solvent in cleaning_solvents:
            # If solvent found add it
            if cleaning_solvent:
                solvents.append(cleaning_solvent)
            # If unknown organic solvent found
            elif cleaning_solvent == GENERIC_ORGANIC:
                organic_solvents = [solvent
                                    for solvent in cleaning_solvents
                                    if solvent and 'water' not in solvent]
                # If there is another organic solvent associated with another
                # reagent from vessel contents, use this.
                if organic_solvents:
                    solvents.append(organic_solvents[0])
                # If there are no other organic solvents associated with the
                # reagents in vessel contents, use a random organic solvent.
                else:
                    organic_solvents = [solvent
                                        for solvent in available_solvents
                                        if 'water' not in solvent]
                    if organic_solvents:
                        solvents.append(organic_solvents[0])
    return solvents

def add_vessel_cleaning_steps(
    xdl_obj: 'XDL',
    hardware: Hardware,
    interactive: bool
) -> 'XDL':
    """Add CleanVessel steps to xdl_obj at appropriate places. Rule is that a
    CleanVessel step should be added after a vessel has been emptied only if the
    step before the emptying step was a Dissolve step. This ensures that any
    solids in the vessel have also been removed before cleaning.

    Args:
        xdl_obj (XDL): XDL object to add CleanVessel steps to.

    Returns:
        XDL: XDL object with CleanVessel steps added at appropriate places.
    """
    clean_vessel_sequence = get_clean_vessel_sequence(xdl_obj, hardware)
    if clean_vessel_sequence:
        for i, vessel, solvent in reversed(clean_vessel_sequence):
            # If organic_cleaning_solvent is given use it otherwise use solvent
            # in synthesis.
            if ('water' not in solvent
                    and xdl_obj.executor._organic_cleaning_solvent):
                solvent = xdl_obj.executor._organic_cleaning_solvent
            xdl_obj.steps.insert(i, CleanVessel(vessel=vessel, solvent=solvent))
    if interactive:
        xdl_obj.steps = suggest_additional_clean_vessel_steps(xdl_obj)
    xdl_obj.steps = add_clean_vessel_temps(xdl_obj.steps)
    xdl_obj.steps = move_non_essential_clean_vessel_steps_to_end(xdl_obj.steps)
    return xdl_obj

def add_clean_vessel_temps(steps: List[List[Step]]) -> List[List[Step]]:
    """Add temperatures to CleanVessel steps. Priority is:
    1) Use explicitly given temperature.
    2) If solvent boiling point known use 80% of the boiling point.
    3) Use 30°C.

    Args:
        steps (List[List[Step]]): List of steps to add temperatures to
            CleanVessel steps

    Returns:
        List[List[Step]]: List of steps with temperatures added to CleanVessel
            steps.
    """
    for step in steps:
        if type(step) == CleanVessel:
            if step.temp is None:
                solvent = step.solvent.lower()
                if solvent in SOLVENT_BOILING_POINTS:
                    step.temp = (SOLVENT_BOILING_POINTS[solvent]
                                 * CLEAN_VESSEL_BOILING_POINT_FACTOR)
                else:
                    step.temp = 30
    return steps

def move_non_essential_clean_vessel_steps_to_end(
        steps: List[List[Step]]) -> List[List[Step]]:
    """If vessel is being cleaned but not needed later on in the procedure do
    the cleaning at the end so the synthesis is not interrupted.
    """
    steps_to_move = []
    for i, step in enumerate(steps):
        if type(step) == CleanVessel:
            vessel = step.vessel
            j = i + 1
            move_to_end = True
            if j >= len(steps):
                move_to_end = False
            else:
                while j < len(steps):
                    if type(steps[j]) == CleanVessel:
                        j += 1
                        continue
                    if vessel in steps[j].properties.values():
                        move_to_end = False
                        break
                    j += 1
            if move_to_end:
                steps_to_move.append(i)

    for i in reversed(steps_to_move):
        steps.append(steps.pop(i))

    return steps

####################################
# Interactive Solvent Verification #
####################################

def verify_cleaning_steps(xdl_obj: 'XDL') -> 'XDL':
    """Allow user to see cleaning steps being added and make changes to what
    solvents are used.

    Args:
        xdl_obj (XDL): XDL object to verify cleaning steps.

    Returns:
        xdl_obj (XDL): XDL object with cleaning steps amended according to user
            input.
    """
    for cleaning_step_type in [CleanBackbone, CleanVessel]:
        logger = get_logger()
        if cleaning_step_type == CleanBackbone:
            name = 'CleanBackbone'
        else:
            name = 'CleanVessel'
        logger.info(f'\n\nVerifying {name} Steps\n--------------------------\
---\n')
        logger.info(f'* {name} solvent indicates the step which is being \
verified. Other steps are shown for context.\n\n')
        solvents = get_available_solvents(xdl_obj)
        chunks = get_cleaning_chunks(xdl_obj, step_type=cleaning_step_type)
        logger.info('Procedure Start')
        for chunk in chunks:
            for i in range(len(chunk)):
                if type(chunk[i]) == cleaning_step_type:
                    logger.info('---------------\n')
                    for j, step in enumerate(chunk):
                        if j == i:
                            logger.info(f'* {name} {step.solvent}')
                        elif type(step) == cleaning_step_type:
                            logger.info(f'{name} {step.solvent}')
                        else:
                            logger.info(step.human_readable())
                    answer = None
                    # Get appropriate answer.
                    while answer not in ['', 'y', 'n']:
                        answer = input(
                            f'\nIs {chunk[i].solvent} an appropriate cleaning \
solvent? ([y], n)\n')
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
                                logger.info('Input must be number corresponding\
to solvent.')
                        # Change step solvent.
                        chunk[i].solvent = solvents[new_solvent_index]
                        logger.info(f'Solvent changed to {chunk[i].solvent}\n')
                        time.sleep(1)


def get_cleaning_chunks(xdl_obj: 'XDL', step_type: Step) -> List[List[Step]]:
    """Takes slices out of xdl_obj steps showing context of cleaning. Chunks
    are the step before a set of CleanBackbone steps, the CleanBackbone steps,
    and the step straight after, e.g. [Add, CleanBackbone, CleanBackbone, Add]

    Arguments:
        xdl_obj (XDL): XDL object to get cleaning chunks from.

    Returns:
        List[List[Step]]: List of slices from xdl_obj steps showing immediate
            context of all CleanBackbone steps.
    """
    chunks = []
    steps = xdl_obj.steps
    i = 0
    while i < len(steps):
        if type(steps[i]) == step_type:
            chunk_start = i
            if i > 0:
                chunk_start = i - 1
            chunk_end = i
            while (chunk_end < len(steps)
                   and type(steps[chunk_end]) == step_type):
                chunk_end += 1
            chunks.append(steps[chunk_start:chunk_end + 1])
            i = chunk_end
        i += 1
    return chunks

#######################################################
# Interactive Suggestion of Additional Cleaning Steps #
#######################################################

def suggest_additional_clean_vessel_steps(xdl_obj: 'XDL') -> List[Step]:
    """Suggest additional CleanVessel steps to user after all contents
    transferred out of a given vessel.

    Args:
        xdl_obj (XDL): XDL object to verify cleaning steps.

    Returns:
        List[Step]: List of steps with new CleanVessel steps included.
    """
    suggest = None
    while suggest not in ['y', 'n', '']:
        suggest = input(
            '\n\nReview suggested vessel cleaning steps? (y, [n])\n')
    if suggest != 'y':
        return xdl_obj.steps

    # insert cleaning steps where instructed to do so interactively
    available_solvents = get_available_solvents(xdl_obj)
    for i, step in enumerate(xdl_obj.steps):
        if step.name == 'Transfer' and step.properties['volume'] == 'all':
            answer = None
            while answer not in ['y', 'n', '']:
                msg = '\nClean vessel after this step? (y, [n])\n'
                msg += f'\n  {step.name}'
                msg += ''.join(
                    [f'\n    {k}: {v}' for k, v in step.properties.items()]
                ) + '\n'
                answer = input(msg)
                if answer == 'y':
                    choice = None
                    while not choice or choice not in available_solvents:
                        msg = 'Which solvent should be used?\n\n'
                        msg += '\n'.join(
                            [f'    {solvent}' for solvent in available_solvents]
                        ) + '\n'
                        choice = input(msg)

                    xdl_obj.steps.insert(
                        (i + 1),
                        CleanVessel(vessel=step.from_vessel, solvent=choice)
                    )
                else:
                    continue
    return xdl_obj.steps
