import os
import pytest
import functools
from ...utils import generic_chempiler_test, XDLStory

from xdl import XDL
from xdl.steps import Wait
from chemputerxdl.steps import Transfer, StartStir, StopStir, CMove, Repeat

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_transfer_through():
    """Test that transfering through a cartridge works."""
    xdl_f = os.path.join(FILES, 'transfer_through.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')

    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_transfer_all_stops_stirring():
    """Test that Transfer 'all' stops stirring, so that stirrer doesn't mess
    with tubing position inside flask.
    """
    xdl_f = os.path.join(FILES, 'transfer_all_stops_stirring.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    transfer_steps = [step for step in x.steps if step.name == 'Transfer']

    # Transfer 10 mL
    assert (
        transfer_steps[0].steps[0].name == 'StopStir'
        and transfer_steps[0].steps[0].vessel == transfer_steps[0].from_vessel
    )
    # Transfer 'all'
    assert (
        transfer_steps[1].steps[0].name == 'StopStir'
        and transfer_steps[1].steps[0].vessel == transfer_steps[1].from_vessel
    )
    assert transfer_steps[1].steps[-3].name == 'StopHeatChill'
    assert transfer_steps[1].steps[-3].vessel == 'reactor'
    assert transfer_steps[1].steps[-2].name == 'StopStir'
    assert transfer_steps[1].steps[-2].vessel == 'reactor'
    assert transfer_steps[1].steps[-1].name == 'StopStir'
    assert transfer_steps[1].steps[-1].vessel == 'rotavap'

    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_transfer_rinse():
    """
    Tests rinse steps in Transfer
    """
    xdl_f = os.path.join(FILES, 'transfer_all_stops_stirring.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    #  get transfer steps. There should only be 2
    transfer_steps = [step for step in x.steps if step.name == 'Transfer']
    assert len(transfer_steps) == 2

    #  for each transfer step, get the substeps relevant to rinsing and check
    #  that rinsing volumes and withdrawal volumes are correct
    for i, transfer_step in enumerate(transfer_steps):

        #  rinse steps are CMove wrapped in repeat => retrieve here
        repeat_step = [
            step for step in transfer_step.steps if step.name == "Repeat"][0]

        #  In each rinse step, the first CMove substep adds rinsing solvent. Get
        #  rinsing solvent addition step
        add_rinse_step = repeat_step.children[0]

        #  In each rinse step, the second CMove substeps aspirated rinsing
        #  solvent (along with whatever residue it has dissolved). Get rinsing
        #  solvent aspiration step
        aspirate_rinse_step = repeat_step.children[1]

        #  The first transfer step should have a rinsing solvent volume of 1 mL
        #  with 20% excess withdrawal volume (i.e. 1.2 mL aspiration). Lower
        #  absolute limit for aspirating rinsing solvent is 2 mL
        if i == 0:
            add_volume = 1
            withdraw_volume = 2
        else:

            #  The second (and final) transfer step should have a rinsing volume
            #  of 20 mL with 20% excess withdrawl volume (i.e. 24 mL aspiration)
            add_volume = 20
            withdraw_volume = 24

        #  check the correct volume of rinsing solvent is being added
        assert add_rinse_step.volume == add_volume

        #  check the correct volume is being aspirated after rinsing
        assert aspirate_rinse_step.volume == withdraw_volume

@pytest.mark.unit
def test_rinse_stirring():
    """Test for stirring during Transfer step.
    """
    xdl_f = os.path.join(GLOBAL_FILES, 'transfer_all_transfer_rinse_stir.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    #  get Transfer steps
    transfers = [s for s in x.steps if type(s) == Transfer]
    assert len(transfers) == 6

    #  ordinary stirs and rinse stirs for each Transfer substep, in order
    stirs_to_vessel = [False, True, False, True, False, True]
    stirs_from_vessel = [False, False, False, False, True, True]
    rinse_stirs = [False, False, True, True, True, True]

    #  check each Transfer step
    for i, transfer_step in enumerate(transfers):

        # Check the from_vessel stir step is correct
        if stirs_from_vessel[i]:
            assert type(transfer_step.steps[0]) == StartStir
        else:
            assert type(transfer_step.steps[0]) == StopStir

        # Check the to_vessel stir step is correct
        if stirs_to_vessel[i]:
            assert type(transfer_step.steps[1]) == StartStir
        else:
            assert type(transfer_step.steps[1]) == StopStir

        assert transfer_step.stir_to_vessel == stirs_to_vessel[i]
        assert transfer_step.stir_from_vessel == stirs_from_vessel[i]
        assert transfer_step.rinse_stir == rinse_stirs[i]

        #  substeps without any stirring, regular stirring and finally rinse
        #  stirring (NOTE: rinse stirring == rinse stirring ONLY)
        substeps = [StopStir, StopStir, CMove, Repeat, StopStir, StopStir]
        stir_substeps = [StopStir, StartStir, CMove, Repeat, StopStir, StopStir]
        rstir_substeps = [StopStir, StopStir, CMove, Repeat, StopStir, StopStir]

        #  get final rinsing steps
        repeat_steps = transfer_step.steps[-3].steps

        #  rinsing substeps with rinse stir
        stirred_rinse = [StartStir, CMove, Wait, StopStir, Wait, CMove]
        reg_rinse = [CMove, CMove]

        #  get substep types for current Transfer steps
        step_types = [type(s) for s in transfer_step.steps]

        #  check everything is in order with regular to_vessel stirring
        if stirs_to_vessel[i] and not stirs_from_vessel[i]:
            assert step_types == stir_substeps
            if not rinse_stirs[i]:
                assert [type(s) for s in repeat_steps] == reg_rinse

        #  check everything is in order with stirring during rinse
        if rinse_stirs[i] and not stirs_from_vessel[i]:

            if not stirs_to_vessel[i] and not stirs_from_vessel[i]:

                assert step_types == rstir_substeps

            assert [type(s) for s in repeat_steps] == stirred_rinse

            #  check initial StartStir step
            assert repeat_steps[0].stir_speed == transfer_step.stir_speed
            assert repeat_steps[0].vessel == transfer_step.from_vessel

            #  check initial rinsing step
            assert repeat_steps[1].from_vessel == (
                transfer_step.rinsing_solvent_vessel
            )
            assert repeat_steps[1].to_vessel == transfer_step.from_vessel
            assert repeat_steps[1].aspiration_speed == (
                transfer_step.aspiration_speed
            )
            assert repeat_steps[1].dispense_speed == (
                transfer_step.dispense_speed
            )
            assert repeat_steps[1].move_speed == (
                transfer_step.move_speed
            )

            #  Check rinse stir Wait, StopStir and settling Wait steps
            assert repeat_steps[2].time == transfer_step.rinse_stir_time
            assert repeat_steps[3].vessel == transfer_step.from_vessel
            assert repeat_steps[4].time == transfer_step.rinse_settle_time

        #  no stirring of any kind, so assume regular substeps
        if (not stirs_to_vessel[i]
                and not rinse_stirs[i]
                and not stirs_from_vessel[i]):
            assert step_types == substeps


# XDLStory using the 'Black Widow' ChemPU graph
transfer_start_stop_stirring_story = functools.partial(
    XDLStory,
    graph=os.path.join(FILES, 'Black_Widow_ChemPU.json'),
    mark=pytest.mark.unit
)

test_story_transfer_from_reactor_to_rotavap =\
    transfer_start_stop_stirring_story(
        name='transfer_reactor_to_rotavap',
        start=Transfer(
            from_vessel="reactor",
            to_vessel="rotavap",
            volume="90 mL",
            stir_from_vessel="True",
            flush_tubing="True",
            rinsing_solvent="toluene",
            rinsing_volume="4 mL",
            rinsing_repeats="2"
        ),
        substeps=[
            StartStir(vessel="reactor", stir_speed="250 RPM"),
            StopStir(vessel="rotavap"),
            StartStir(vessel="reactor", stir_speed="250 RPM"),
            StopStir(vessel="reactor"),
            StopStir(vessel="rotavap"),
        ],
        not_substeps=[
            StartStir(vessel="rotavap", stir_speed="250 RPM"),
        ],
    )

test_story_transfer_from_rotavap_to_filter = transfer_start_stop_stirring_story(
    name='transfer_reactor_to_rotavap',
    start=Transfer(
        from_vessel="rotavap",
        to_vessel="filter",
        volume="80 mL",
        to_port="top",
        stir_from_vessel="True",
        flush_tubing="True",
        rinsing_solvent="methanol",
        rinsing_volume="7 mL",
        rinsing_repeats="2"
    ),
    substeps=[
        StartStir(vessel="rotavap", stir_speed="250 RPM"),
        StopStir(vessel="filter"),
        StartStir(vessel="rotavap", stir_speed="250 RPM"),
        StopStir(vessel="rotavap"),
        StopStir(vessel="filter"),
    ],
    not_substeps=[
        StartStir(vessel="filter", stir_speed="250 RPM"),
    ],
)

# XDLStory using the 'Vision' ChemPU graph for the first
# two steps of the Arbidol synthesis.
transfer_start_stop_stirring_story_Vision = functools.partial(
    XDLStory,
    graph=os.path.join(FILES, 'Vision_ChemPU_Arbidol.json'),
    mark=pytest.mark.unit
)

test_story_transfer_from_reactor_to_rotavap_Vision_Arbidol =\
    transfer_start_stop_stirring_story_Vision(
        name='transfer_reactor_to_rotavap_no_stirring',
        start=Transfer(
            volume="all",
            from_vessel="reactor_1",
            to_vessel="rotavap",
            rinsing_solvent="ethanol",
            rinsing_volume="20 mL",
            rinsing_repeats="3"
        ),
        substeps=[
            StopStir(vessel="reactor_1"),
            StopStir(vessel="rotavap"),
            StartStir(vessel="reactor_1", stir_speed="250 RPM"),
            StopStir(vessel="reactor_1"),
            StopStir(vessel="reactor_1"),
            StopStir(vessel="rotavap"),
        ],
        not_substeps=[
            StartStir(vessel="rotavap", stir_speed="250 RPM"),
        ],
    )

test_story_transfer_from_rotavap_to_filter_Vision_Arbidol =\
    transfer_start_stop_stirring_story_Vision(
        name='transfer_from_rotavap_to_jacketed_filter_with_stirring',
        start=Transfer(
            from_vessel="rotavap",
            to_vessel="reactor_2",
            dispense_speed="2",
            volume="20 mL",
            rinsing_solvent="1,2-dichloroethane",
            rinsing_volume="2.0 mL",
            rinsing_repeats="3",
            stir_to_vessel="True",
            stir_from_vessel="False"
        ),
        substeps=[
            StopStir(vessel="rotavap"),
            StartStir(vessel="reactor_2", stir_speed="250 RPM"),
            StartStir(vessel="rotavap", stir_speed="250 RPM"),
            StopStir(vessel="rotavap"),
            StopStir(vessel="rotavap"),
            StopStir(vessel="reactor_2"),
        ],
        not_substeps=[
        ],
    )
