import os
import functools
import pytest
from ...utils import generic_chempiler_test, XDLStory


from xdl import XDL
from xdl.errors import XDLSanityCheckError
from chemputerxdl.steps import (
    CleanBackbone,
    Dissolve,
    CleanVessel,
    Separate,
    HeatChillToTemp,
    HeatChillReturnToRT,
    Dry,
    StartStir,
    CRotavapLiftDown,
    CRotavapLiftUp,
)

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')


@pytest.mark.unit
def test_clean_vessel():
    """Test that dissolving a solid in the rotavap works."""
    xdl_f = os.path.join(FILES, 'clean_reactor_rotavap.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_clean_vessel_no_vacuum():
    xdl_f = os.path.join(FILES, 'clean_vessel_no_vacuum.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'orgsyn_v81p0262.json')
    generic_chempiler_test(xdl_f, graph_f)


CLEAN_VESSEL_TESTS = [
    # TODO: Upgrade graphml graphs with "temp_sensor" property
    # (os.path.join(GLOBAL_FILES, 'alkyl_fluor_step4.xdl'),
    #  os.path.join(GLOBAL_FILES, 'alkyl_fluor_step4.graphml'),
    #  None,
    #  2,
    #  ['acetonitrile', 'dcm'],
    #  [81.65 * CLEAN_VESSEL_BOILING_POINT_FACTOR,
    #   39.8 * CLEAN_VESSEL_BOILING_POINT_FACTOR]),

    # (os.path.join(GLOBAL_FILES, 'lidocaine.xdl'),
    #  os.path.join(GLOBAL_FILES, 'lidocaine_graph.json'),
    #  'ether',
    #  1,
    #  ['ether'],
    #  [34.5 * CLEAN_VESSEL_BOILING_POINT_FACTOR]),
]

@pytest.mark.unit
def test_clean_vessel_scheduling():
    """Test that all CleanVessel steps are added at correct places, i.e.
    ...Dissolve, emptying_step, CleanVessel,..."""
    for (xdl_f, graph_f, organic_cleaning_solvent, n_clean_vessels,
         clean_vessel_solvents, clean_vessel_temps) in CLEAN_VESSEL_TESTS:
        print(xdl_f, graph_f)
        x = XDL(xdl_f)
        x.prepare_for_execution(
            graph_f,
            interactive=False,
            organic_cleaning_solvent=organic_cleaning_solvent,
            auto_clean=True,
        )

        # Check right number of steps with right vessel/solvent have been added.
        clean_vessel_steps = [
            step for step in x.steps if type(step) == CleanVessel]
        assert len(clean_vessel_steps) == n_clean_vessels
        for i in reversed(range(len(clean_vessel_steps))):
            print(clean_vessel_steps[i].temp)
            assert(clean_vessel_steps[i].solvent.lower()
                   == clean_vessel_solvents.pop().lower())
            correct_temp = clean_vessel_temps.pop()
            assert clean_vessel_steps[i].temp == correct_temp
            assert type(clean_vessel_steps[i].steps[1]) == HeatChillToTemp
            assert clean_vessel_steps[i].steps[1].temp == correct_temp
            assert type(clean_vessel_steps[i].steps[-1]) == HeatChillReturnToRT

        # Check all CleanVessel steps come after Dissolve + filter_emptying step
        # or after Separate step.
        for i in range(len(x.steps)):
            emptying_step_passed = False
            legit = True
            if type(x.steps[i]) == CleanVessel:
                # Check default double clean is being done.
                assert (len([step
                             for step in x.steps[i].steps
                             if step.name == 'CMove']) == 5)
                legit = False
                j = i
                while j > 0:
                    j -= 1
                    #  Ignore CleanBackbone steps
                    if type(x.steps[j]) == CleanBackbone:
                        continue
                    # Dissolve steps encountered after emptying step.
                    elif type(x.steps[j]) == Dissolve and emptying_step_passed:
                        legit = True
                        break
                    elif type(x.steps[j]) == Separate:
                        legit = True
                        break
                    # Found emptying step.
                    elif not emptying_step_passed:
                        emptying_step_passed = True
                    # Emptying step already found but next step backwards is
                    # not a Dissolve step. Therefore CleanVessel is incorrectly
                    # placed.
                    else:
                        legit = False
                        break
                assert legit

@pytest.mark.unit
def test_clean_vessel_move_to_end():
    xdl_f = os.path.join(FILES, 'clean_vessel_at_end.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, interactive=False, auto_clean=True)

    # Ignore the Shutdown at the end
    check_steps = x.steps[:-1]
    assert len(
        [step for step in check_steps if step.name == 'CleanVessel']) == 1
    assert check_steps[-2].name == 'CleanVessel'
    generic_chempiler_test(xdl_f, graph_f)

###########################
# Clean Vessel Stir Speed #
###########################


# XDLStory using bigrig graph and unit test mark
orgsyn_v81p0262_story = functools.partial(
    XDLStory,
    graph=os.path.join(GLOBAL_FILES, 'orgsyn_v81p0262.json'),
    mark=pytest.mark.unit
)


test_story_rotavap_lift_down_up_clean = orgsyn_v81p0262_story(
    name='Clean vessel in rotavap should start with liftdown and end with up',
    start=CleanVessel(
        vessel='rotavap',
        solvent='hexanes',
        temp=50,
        dry=False
    ),
    substeps=[
        CRotavapLiftDown(rotavap_name='rotavap'),
        HeatChillToTemp(vessel='rotavap', temp=50),
        CRotavapLiftUp(rotavap_name='rotavap'),
    ],
)


test_story_clean_vessel_stir_rotavap = orgsyn_v81p0262_story(
    name='Clean vessel in rotavap should stir at 150 RPM',
    start=CleanVessel(
        vessel='rotavap',
        solvent='hexanes',
        dry=False,
    ),
    substeps=[
        StartStir(vessel='rotavap', stir_speed=CleanVessel.ROTAVAP_STIR_SPEED),
    ],
)

test_story_clean_vessel_stir_hotplate = orgsyn_v81p0262_story(
    name='Clean vessel with hotplate should stir at 250 RPM',
    start=CleanVessel(
        vessel='reactor',
        solvent='hexanes',
        dry=False,
    ),
    substeps=[
        StartStir(vessel='reactor', stir_speed=CleanVessel.HOTPLATE_STIR_SPEED),
    ],
)

test_story_clean_vessel_stir_stirrer = orgsyn_v81p0262_story(
    name='Clean vessel with stirrer should stir at 500 RPM',
    start=CleanVessel(
        vessel='separator',
        solvent='hexanes',
        dry=False,
    ),
    substeps=[
        StartStir(
            vessel='separator', stir_speed=CleanVessel.STIRRER_STIR_SPEED),
    ],
)

############################
# Clean Vessel with Drying #
############################

# XDLStory using bigrig graph and unit test mark
bigrig_story = functools.partial(
    XDLStory,
    graph=os.path.join(GLOBAL_FILES, 'bigrig.json'),
    mark=pytest.mark.unit
)

# Clean vessel with drying, when dry is False

test_story_clean_vessel_dry_false = bigrig_story(
    name='Clean vessel with dry=False should not have Dry substep',
    start=CleanVessel(
        vessel='filter',
        solvent='water',
        dry=False,
    ),
    not_substeps=[Dry],
)

test_story_clean_vessel_dry_false_dry_time = bigrig_story(
    name='Clean vessel should throw error when dry=False and dry time given',
    start=CleanVessel(
        vessel='filter',
        solvent='water',
        dry=False,
        dry_time='3 h'
    ),
    error=XDLSanityCheckError,
)

test_story_clean_vessel_dry_false_dry_temp = bigrig_story(
    name='Clean vessel should throw error when dry=False and dry temp given',
    start=CleanVessel(
        vessel='filter',
        solvent='water',
        dry=False,
        dry_temp=50
    ),
    error=XDLSanityCheckError,
)

# Clean vessel with drying, when dry is None

test_story_clean_vessel_dry_none_rotavap = bigrig_story(
    name='Clean vessel with dry=None in rotavap should dry',
    start=CleanVessel(
        vessel='rotavap',
        solvent='water',
        dry=None,
    ),
    substeps=[
        Dry(
            vessel='rotavap',
            time=CleanVessel.FALLBACK_DRY_TIME,
            temp=CleanVessel.FALLBACK_DRY_TEMP
        )
    ],
)

test_story_clean_vessel_dry_none_rotavap_time_temp = bigrig_story(
    name='Clean vessel with dry=None in filter with params should dry',
    start=CleanVessel(
        vessel='filter',
        solvent='water',
        dry=None,
        dry_time='35 min',
        dry_temp=64
    ),
    substeps=[
        Dry(
            vessel='filter',
            time=35 * 60,
            temp=64
        )
    ],
)

test_story_clean_vessel_dry_none_separator = bigrig_story(
    name='Clean vessel with dry=None and no vacuum available should not dry and not throw error',  # noqa: E501
    start=CleanVessel(
        vessel='separator',
        solvent='water',
        dry=None
    ),
    not_substeps=[Dry]
)

test_story_clean_vessel_dry_none_separator_time = bigrig_story(
    name='Clean vessel with dry=None, dry_time specified and no vacuum available should not dry and should throw error',  # noqa: E501
    start=CleanVessel(
        vessel='separator',
        solvent='water',
        dry=None,
        dry_time='30 min'
    ),
    error=XDLSanityCheckError,
)

test_story_clean_vessel_dry_none_separator_temp = bigrig_story(
    name='Clean vessel with dry=None, dry_temp specified and no vacuum available should not dry and should throw error',  # noqa: E501
    start=CleanVessel(
        vessel='separator',
        solvent='water',
        dry=None,
        dry_temp=74
    ),
    error=XDLSanityCheckError,
)

test_story_clean_vessel_dry_true = bigrig_story(
    name='Clean vessel with dry=True in filter should pass and use default params',  # noqa: E501
    start=CleanVessel(
        vessel='filter',
        solvent='water',
        dry=True,
    ),
    substeps=[
        Dry(
            vessel='filter',
            time=CleanVessel.FALLBACK_DRY_TIME,
            temp=CleanVessel.FALLBACK_DRY_TEMP
        )
    ],
)

test_story_clean_vessel_dry_true_specific_params = bigrig_story(
    name='Clean vessel with dry=True in filter should pass and use given params',  # noqa: E501
    start=CleanVessel(
        vessel='rotavap',
        solvent='water',
        dry=True,
        dry_time=2762,
        dry_temp=31,
    ),
    substeps=[
        Dry(
            vessel='rotavap',
            time=2762,
            temp=31
        )
    ],
)

test_story_clean_vessel_dry_true_no_vacuum = bigrig_story(
    name='Clean vessel with dry=True but no vacuum available should throw error',  # noqa: E501
    start=CleanVessel(
        vessel='separator',
        solvent='water',
        dry=True,
    ),
    error=XDLSanityCheckError
)
