import os
import pytest
import functools
from xdl import XDL
from chemputerxdl.steps import (
    Transfer, Add, Stir, Wait, Separate, SeparatePhases)
from ...utils import test_step, XDLStory
from xdl.errors import XDLError
from xdl.utils.sanitisation import convert_val_to_std_units

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')
TESTOUTPUT = os.path.join(HERE, "test_output")
os.makedirs(TESTOUTPUT, exist_ok=True)

correct_step_info = [
    # Product bottom, single wash
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator'
        }),
        (Transfer, {})
    ],
    # Product top, single wash
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'rotavap',
            'upper_phase_port': 'evaporate',
        }),
        (Transfer, {}),  # added in safe mode
    ],
    # Product bottom, single extraction
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator'
        }),
        (Transfer, {})  # Added in safe mode
    ],
    # Product top, single extraction
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'rotavap',
            'upper_phase_port': 'evaporate',
        }),
        (Transfer, {}),  # added in safe mode
    ],
    # Product bottom, 2 washes
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
        (Add, {}),
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator'
        }),
        (Transfer, {}),  # Added in safe mode
    ],
    # Product top, 2 washes
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'separator',
        }),
        (Transfer, {}),  # added in safe mode
        (Add, {}),
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'upper_phase_vessel': 'rotavap',
            'upper_phase_port': 'evaporate',
            'lower_phase_vessel': 'buffer_flask'
        }),
        (Transfer, {}),  # added in safe mode
    ],
    # Product bottom, 2 extractions
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'separator',
        }),
        (Transfer, {}),  # Added in safe mode
        (Add, {}),
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator',
        }),
        (Transfer, {}),  # Added in safe mode
    ],
    # Product top 2, extractions
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'rotavap',
            'upper_phase_port': 'evaporate',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
        (Add, {}),
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'upper_phase_vessel': 'rotavap',
            'upper_phase_port': 'evaporate',
            'lower_phase_vessel': 'buffer_flask'
        }),
        (Transfer, {}),  # added in safe mode
    ],

    # Product bottom 1 wash, to_vessel == separation_vessel
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
    ],

    # Product bottom 1 extraction, to_vessel == separation_vessel
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
    ],

    # Product top 1 wash, to_vessel == separation_vessel
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'separator',
        }),
        (Transfer, {}),  # added in safe mode
    ],

    # Product top 1 extraction, to_vessel == separation_vessel
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'separator',
        }),
        (Transfer, {}),  # added in safe mode
    ],

    # Product top 2 wash, to_vessel == separation_vessel
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'separator',
        }),
        (Transfer, {}),  # added in safe mode
        (Add, {}),
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'upper_phase_vessel': 'separator',
            'lower_phase_vessel': 'buffer_flask'
        }),
        (Transfer, {}),  # added in safe mode
    ],

    # Product bottom 2 wash, to_vessel == separation_vessel
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
        (Add, {}),
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
    ],

    # Product top 2 extractions, to_vessel == separation_vessel
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'buffer_flask2',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
        (Add, {}),
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',  # changed in safe_mode
            'upper_phase_vessel': 'separator',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask2',
            'to_vessel': 'separator',
        }),
        (Transfer, {  # added in safe_mode
            'from_vessel': 'buffer_flask',
            'to_vessel': 'waste_separator',
        }),
    ],

    # Product bottom 2 extractions, to_vessel == separation_vessel
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'separator',
        }),
        (Add, {}),
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
    ],

    # Product top, 1 extraction, waste phase to separator, product phase to
    # rotavap
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'rotavap',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
    ],

    # Product top, 2 extractions, waste_phase_to_separator, product phase to
    # rotavap
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'rotavap',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
        (Add, {}),  # Solvent
        (Stir, {
            'stir_speed': convert_val_to_std_units(
                Separate.DEFAULT_PROPS['stir_speed']),
            'time': convert_val_to_std_units(
                Separate.DEFAULT_PROPS['stir_time'])
        }),
        (Stir, {}),
        (Wait, {
            'time': convert_val_to_std_units(
                Separate.DEFAULT_PROPS['settling_time'])
        }),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'rotavap',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
    ],

    # Product top, 2 washes, waste_phase_to_separator, product phase to
    # rotavap
    [
        (Transfer, {}),  # Reaction mixture
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'separator',
        }),
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'rotavap',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
    ],

    # Product top, 2 washes, waste_phase_to_waste, product phase to
    # rotavap
    [
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'waste_separator',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'rotavap',
            'through': 'celite'
        }),
    ],

    # Product bottom, 2 washes, waste phase to separator,
    # product phase to rotavap
    [
        (Transfer, {
            'from_vessel': 'filter',
            'to_vessel': 'separator',
        }),
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'buffer_flask2',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'separator',
        }),
        (Add, {}),  # Solvent
        (Stir, {}),
        (Stir, {}),
        (Wait, {}),
        (SeparatePhases, {
            'lower_phase_vessel': 'buffer_flask',
            'upper_phase_vessel': 'buffer_flask2',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask',
            'to_vessel': 'rotavap',
        }),
        (Transfer, {
            'from_vessel': 'buffer_flask2',
            'to_vessel': 'separator',
        })
    ]
]

@pytest.mark.unit
def test_separate():
    """Test separating then moving through a cartridge to the final vessel."""
    xdl_f = os.path.join(FILES, 'separate.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    # generic_chempiler_test(xdl_f, graph_f)
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    assert (
        len([step for step in x.steps if step.name == 'Separate'])
        == len(correct_step_info)
    )
    i = 0
    for step in x.steps:
        if type(step) == Separate:
            current_step_info = correct_step_info[i]
            try:
                assert len(current_step_info) == len(step.steps)
            except AssertionError:
                raise AssertionError(
                    f'Step: {i} ({len(current_step_info)} {len(step.steps)})\n\
 {step.properties}\n\n{current_step_info}')
            for j, substep in enumerate(step.steps):
                try:
                    test_step(substep, current_step_info[j])
                except AssertionError:
                    raise AssertionError(
                        f'Step: {i} {step.properties}\n\n{substep.properties}')
            i += 1
    assert i == len(correct_step_info)

@pytest.mark.unit
def test_separate_without_enough_buffer_flasks():
    with pytest.raises(XDLError):
        xdl_f = os.path.join(FILES, 'separate_no_buffers.xdl')
        graph_f = os.path.join(FILES, 'separate_no_buffers.json')
        x = XDL(xdl_f)
        x.prepare_for_execution(graph_f, testing=True)

@pytest.mark.unit
def test_separate_more_than_max_volume():
    xdl_f = os.path.join(FILES, 'separate_more_than_max_volume.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if step.name == 'Separate':
            assert step.repeats == 2
            assert step.solvent_volume == 75

# Story testing safe mode


bigrig_story = functools.partial(
    XDLStory,
    graph=os.path.join(GLOBAL_FILES, 'bigrig.json'),
    mark=pytest.mark.unit
)

# in the next 4 tests, "default" refers to the state of "safe_mode"

test_story_default_mode_final_extract = bigrig_story(
    name='Test default mode in the "safe" update with mulit top-exatraction',
    save=os.path.join(TESTOUTPUT, "default_mode_extract_final.xml"),
    start=Separate(
        repeats=2,
        purpose='extract',
        separation_vessel='separator',
        from_vessel='reactor',
        to_vessel='separator',
        solvent='water',
        solven_volume='20',
        product_phase='top',
        stir_time='300',
    ),
    not_substeps=[
        SeparatePhases(
            separation_vessel="separator",
            lower_phase_vessel="waste_separator",  # will be buffer instead
            upper_phase_vessel="separator",
            dead_volume_vessel="waste_separator",
            lower_phase_port="0",
            upper_phase_port="bottom",
            dead_volume_port="0",
            failure_vessel="separator",
            max_retries="2",
            lower_phase_through_cartridge="None",
            can_retry="False",
            separation_vessel_max_volume="100.0",
            separation_vessel_pump="pump_separator",
            pump_max_volume="100.0",
            conductivity_sensor="conductivity_sensor",
            high_conductivity_phase="bottom",
        )
    ]
)


test_story_default_mode_multi_extract = bigrig_story(
    name='Test default mode in the "safe" update with mulit bottom-exatraction',
    save=os.path.join(TESTOUTPUT, "default_mode_extract.xml"),
    start=Separate(
        repeats=2,
        purpose='extract',
        separation_vessel='separator',
        from_vessel='reactor',
        to_vessel='rotavap',
        solvent='water',
        solven_volume='20',
        product_phase='bottom',
        stir_time='300',
    ),
    not_substeps=[
        SeparatePhases(
            separation_vessel="separator",
            lower_phase_vessel="rotavap",  # will be buffer instead
            upper_phase_vessel="waste_separator",
            dead_volume_vessel="waste_separator",
            lower_phase_port="evaporate",
            upper_phase_port="0",
            dead_volume_port="0",
            failure_vessel="rotavap",
            max_retries="2",
            lower_phase_through_cartridge="None",
            can_retry="True",
            separation_vessel_max_volume="100.0",
            separation_vessel_pump="pump_separator",
            pump_max_volume="100.0",
            conductivity_sensor="conductivity_sensor",
            high_conductivity_phase="top",
        )
    ]
)

test_story_default_mode_multi_wash = bigrig_story(
    name='Test the default mode in the "safe" update with multi washing',
    save=os.path.join(TESTOUTPUT, "default_mode_wash.xml"),
    start=Separate(
        repeats=2,
        purpose='wash',
        separation_vessel='separator',
        from_vessel='reactor',
        to_vessel='rotavap',
        solvent='water',
        solven_volume='20',
        product_phase='top',
        stir_time='300',
        waste_phase_to_vessel_to_use="waste_separator"
    ),
    not_substeps=[
        SeparatePhases(
            separation_vessel="separator",
            lower_phase_vessel="waste_separator",  # will be buffer instead
            upper_phase_vessel="rotavap",
            dead_volume_vessel="waste_separator",
            lower_phase_port="0",
            upper_phase_port="evaporate",
            dead_volume_port="0",
            failure_vessel="rotavap",
            max_retries="2",
            lower_phase_through_cartridge="None",
            can_retry="False",
            separation_vessel_max_volume="100.0",
            separation_vessel_pump="pump_separator",
            pump_max_volume="100.0",
            conductivity_sensor="conductivity_sensor",
        )
    ]
)

test_story_default_mode_single_extract = bigrig_story(
    name='Test the default mode in the "safe" update with single extract top',
    save=os.path.join(TESTOUTPUT, "default_mode_single_extract.xml"),
    start=Separate(
        repeats=1,
        purpose='extract',
        separation_vessel='separator',
        from_vessel='reactor',
        to_vessel='rotavap',
        solvent='water',
        solven_volume='20',
        product_phase='top',
        stir_time='300',
        waste_phase_to_vessel_to_use="waste_separator"
    ),
    not_substeps=[
        SeparatePhases(
            separation_vessel="separator",
            lower_phase_vessel="waste_separator",  # will be buffer instead
            upper_phase_vessel="rotavap",
            dead_volume_vessel="waste_separator",
            lower_phase_port="0",
            upper_phase_port="evaporate",
            dead_volume_port="0",
            failure_vessel="rotavap",
            max_retries="2",
            lower_phase_through_cartridge="None",
            can_retry="False",
            separation_vessel_max_volume="100.0",
            separation_vessel_pump="pump_separator",
            pump_max_volume="100.0",
            conductivity_sensor="conductivity_sensor",
        )
    ]
)
