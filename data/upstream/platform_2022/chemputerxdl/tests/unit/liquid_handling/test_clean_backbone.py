import os
import pytest
import functools
from ...utils import generic_chempiler_test

from xdl import XDL
from chemputerxdl.steps import CleanBackbone, Add, ResetHandling, CMove
from chemputerxdl.executor.errors import XDLNoSolventsError
from ...utils import XDLStory

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

lidocaine_story = functools.partial(
    XDLStory,
    mark=pytest.mark.unit,
    graph=os.path.join(GLOBAL_FILES, 'lidocaine_graph.json')
)

#####################
# Cleaning Schedule #
#####################

ALKYL_FLUOR_STEP4_CLEANING_SCHEDULE = [
    'acetonitrile',
    # Dry
    'acetonitrile',
    # AddFilterDeadVolume acetonitrile
    # 'acetonitrile',
    # Add acetonitrile
    # 'acetonitrile',
    # Dissolve acetonitrile
    # 'acetonitrile',
    # Transfer
    'acetonitrile',
    # CleanVessel
    'acetonitrile',
    'dcm',
    # HeatChill, HeatChillReturnToRT
    # FilterThrough
    'dcm',
    # Evaporate
    # Dissolve DCM
    # 'dcm',
    # FilterThrough DCM
    'dcm',
    # CleanVessel
    'dcm',
    # Transfer
    'dcm',
    'ether',
    # WashSolid
    'ether',
    # Dry
    'ether',
    'acetonitrile'
]

EXPENSIVE_SOLVENTS = [
    "ethyl vinyl ether"
]

# TODO: Upgrade graphml graphs with "temp_sensor" property
# @pytest.mark.unit
def test_cleaning_schedule():
    """Test that cleaning scheduling algorithm works correctly."""
    xdl_f = os.path.join(GLOBAL_FILES, 'alkyl_fluor_step4.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'alkyl_fluor_step4.graphml')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, interactive=False, auto_clean=True)
    cleaning_solvents = [
        step.solvent for step in x.steps if type(step) == CleanBackbone]
    for solvent in cleaning_solvents:
        print(solvent)
    for i in range(len(cleaning_solvents)):
        assert (ALKYL_FLUOR_STEP4_CLEANING_SCHEDULE[i].lower()
                == cleaning_solvents[i].lower())

@pytest.mark.unit
def test_cleaning_no_solvents():
    """Test that having no solvents available doesn't cause an error."""
    xdl_f = os.path.join(FILES, 'no_cleaning_solvents.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, interactive=False, auto_clean=True)

def test_cleaning_no_solvents_but_cleaning_needed():
    xdl_f = os.path.join(FILES, 'no-cleaning-solvents-cleaning-required.xdl')
    graph_f = os.path.join(
        FILES, 'no-cleaning-solvents-cleaning-required.json')
    x = XDL(xdl_f)
    with pytest.raises(XDLNoSolventsError):
        x.prepare_for_execution(graph_f, interactive=False, auto_clean=True)

@pytest.mark.unit
def test_cleaning_no_preserved_solvents():
    """ Tests that this routine does not use the expensive solvent
    ethyl vinyl ether
    """

    xdl_f = os.path.join(FILES, "no_expensive_solvents.xdl")
    graph_f = os.path.join(FILES, "no_expensive_solvents.json")
    generic_chempiler_test(xdl_f, graph_f)

    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, interactive=False, auto_clean=True)

    for step in x.steps:
        if isinstance(step, CleanBackbone):
            assert step.solvent not in EXPENSIVE_SOLVENTS

# @pytest.mark.unit
# DEPRECATED: Not used by new XDL Standard 0.5.
def test_incompatible_solvents_reagents_dcm():
    """
    Tests whether solvents incompatible with specific reagents are ruled out
    of cleaning (if otherwise appropriate). In this case, cleaning solvent
    should be dcm for all CleanBackbone steps.
    """

    xdl_f_dcm = os.path.join(
        FILES,
        "incompatible_reagent_solvents_clean_dcm.xdl")
    graph_f_dcm = os.path.join(FILES, "reagent_solvents_graph.json")
    generic_chempiler_test(xdl_f_dcm, graph_f_dcm)

    x_dcm = XDL(xdl_f_dcm)
    x_dcm.prepare_for_execution(graph_f_dcm, interactive=False, auto_clean=True)

    cleans = [
        [j, step.solvent] for j, step in enumerate(x_dcm.steps)
        if type(step) == CleanBackbone]

    for j, step in enumerate(x_dcm.steps):
        if type(step) == Add:
            next_clean_solvent = [
                clean for clean in cleans
                if clean[0] > j][0][1]
            previous_clean_solvent = [
                clean for clean in cleans
                if clean[0] < j][-1][1]
            if step.reagent == 'ala':
                assert next_clean_solvent == "dcm"
                assert previous_clean_solvent == "dcm"
            elif step.reagent in ["pip", "substrateS3"]:
                assert next_clean_solvent == "ether"

@pytest.mark.unit
def test_basic_reagents():
    """
    Tests whether an extra backbone cleaning step is applied after addition of
    a basic reagent. Two XDLs are used to test this, each identical with the
    exception of two reagents (substrateS3 and ala) being defined as
    bases in the "_dcm_base" XDL.
    """
    xdl_f_dcm = os.path.join(
        FILES,
        "incompatible_reagent_solvents_clean_dcm.xdl")
    xdl_f_dcm_base = xdl_f_dcm.replace("_dcm", "_dcm_base")

    graph_f_dcm = os.path.join(FILES, "reagent_solvents_graph.json")

    generic_chempiler_test(xdl_f_dcm, graph_f_dcm)
    generic_chempiler_test(xdl_f_dcm_base, graph_f_dcm)

    x_dcm = XDL(xdl_f_dcm)
    x_dcm_base = XDL(xdl_f_dcm_base)

    x_dcm.prepare_for_execution(graph_f_dcm, interactive=False, auto_clean=True)
    x_dcm_base.prepare_for_execution(
        graph_f_dcm, interactive=False, auto_clean=True)

    reagents = ["substrateS3", "ala", "pip", "dcm"]

    for reagent_id in reagents:
        addition_step_non_base = [
            k for k, step in enumerate(x_dcm.steps)
            if type(step) == Add and step.reagent == reagent_id][0]
        addition_step_base = [
            k for k, step in enumerate(x_dcm_base.steps)
            if type(step) == Add and step.reagent == reagent_id][0]
        post_cleans_base = len([
            k for k, step in enumerate(x_dcm_base.steps)
            if type(step) == CleanBackbone and k > addition_step_base])
        post_cleans_non_base = len([
            k for k, step in enumerate(x_dcm.steps)
            if type(step) == CleanBackbone and k > addition_step_non_base])
        if reagent_id in ["pip", "ala"]:
            assert post_cleans_base == post_cleans_non_base + 3
        else:
            assert post_cleans_base == post_cleans_non_base + 1


test_clean_backbone_story_repeats = lidocaine_story(
    name='Clean backbone repeats should be passed down to CMove step',
    start=ResetHandling(solvent='water', repeats=5),
    substeps=[CMove(
        from_vessel='flask_water',
        to_vessel='waste_base',
        from_port=0,
        to_port=0,
        volume=CleanBackbone.DEFAULT_PROPS['volume'],
        repeats=5
    )]
)

test_clean_backbone_story_volume = lidocaine_story(
    name='Clean backbone volume should be passed down to CMove step',
    start=ResetHandling(solvent='water', volume=20),
    substeps=[CMove(
        from_vessel='flask_water',
        to_vessel='waste_base',
        from_port=0,
        to_port=0,
        volume=20,
        repeats=ResetHandling.DEFAULT_PROPS['repeats']
    )]
)
