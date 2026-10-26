import os
import pytest
from xdl import XDL
from chemputerxdl.steps import (
    MWAddAndTurn,
    CTurnMotor,
    Transfer,
    RepeatCleanMW,
    HarvestWheel,
    CHomeMotor,
    CMove,
    CMoveMotor
)
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

@pytest.mark.unit
def test_modular_wheel_execution():
    """Tests MWAddAndTurn step.
    """
    xdl_f = os.path.join(FILES, "modular_wheel_transfer.xdl")
    graph_f = os.path.join(FILES, "modular_wheel.json")
    generic_chempiler_test(xdl_f, graph_f)

    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, interactive=False)

    assert isinstance(x.steps[0], MWAddAndTurn)

    for step in x.steps:
        if isinstance(step, MWAddAndTurn):
            assert len(step.steps) == 2
            assert isinstance(step.steps[0], Transfer)
            assert isinstance(step.steps[-1], CTurnMotor)
            assert step.motor_steps == 3200

@pytest.mark.unit
def test_modular_wheel_repeat():
    """Tests the modular wheel RepeatCleanMW step.
    """
    xdl_f = os.path.join(FILES, "modular_wheel_repeat.xdl")
    graph_f = os.path.join(FILES, "modular_wheel_syringe.json")
    generic_chempiler_test(xdl_f, graph_f)

    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, interactive=False)

    assert type(x.steps[0]) == RepeatCleanMW

    assert x.steps[0].n_positions == 6

    repeat_clean_steps = x.steps[0].steps
    assert len(repeat_clean_steps) == 24

    #  break into chunks: one chunk == one block of repeats
    chunks = [
        repeat_clean_steps[i: i + 3]
        for i in range(0, len(repeat_clean_steps), 3)
    ]
    assert len(chunks) == 8

    #  values for n_turns, turn_first props for one full cycle of wheel
    turns = [(1, 1, 2), (0, 2, 3), (0, 3, 2), (0, 2, 1), (0, 1, 0), (1, 1, 2)]
    turn_first = [
        (True, True),
        (False, True),
        (False, True),
        (False, True),
        (False, True),
        (True, True)
    ]

    #  (sample volume, MW clean volume)
    volumes = (10, 1)

    #  iterate through repeat blocks, ensuring values for n_turns, turn_first
    #  amd volumes are correct
    for i, chunk in enumerate(chunks):

        assert [type(step) for step in chunk] == [
            MWAddAndTurn, MWAddAndTurn, CTurnMotor]

        if i > 5:
            i = (i + 1) % 6

        for j, step in enumerate(chunk):

            assert step.reverse_first == step.reverse_after
            assert step.wait_reverse == 1
            assert step.wait_turn == 3
            if j < 2:
                assert step.volume == volumes[j]
                assert step.turn_first == turn_first[i][j]
            assert step.n_turns == turns[i][j]
            if j == 1:
                assert step.from_vessel == "water"

@pytest.mark.unit
def test_modular_wheel_harvest():
    """Tests HarvestWheel step for Modular Wheel and Modular Syringe.
    """
    xdl_f = os.path.join(FILES, "modular_wheel_harvest.xdl")
    graph_f = os.path.join(FILES, "modular_wheel_syringe.json")
    generic_chempiler_test(xdl_f, graph_f)

    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, interactive=False)

    harvest_step = x.steps[0]
    assert type(harvest_step) == HarvestWheel

    #  make sure internal props are correct
    assert harvest_step.z_step_distance == 1500
    assert harvest_step.xy_step_distance == 40500
    assert harvest_step.device_name == 'modular_wheel'

    #  make sure there are no turns
    assert harvest_step.n_turns == 0

    #  check order of homing and motor movement is correct for modular syringe
    for i, step in enumerate(harvest_step.steps):
        if i in [0, 1, 5, 6]:
            assert type(step) == CHomeMotor
        elif i == 4:
            assert type(step) == CMove
            assert step.from_vessel == 'modular_syringe'
            assert step.volume == 10
        else:
            assert type(step) == CMoveMotor
        if i in [0, 3, 5]:
            assert step.motor_name == 'modular_z'
            if i == 3:
                assert step.motor_steps == harvest_step.z_step_distance
        elif i in [1, 2, 6]:
            assert step.motor_name == 'modular_xy'
            if i == 2:
                assert step.motor_steps == harvest_step.xy_step_distance
