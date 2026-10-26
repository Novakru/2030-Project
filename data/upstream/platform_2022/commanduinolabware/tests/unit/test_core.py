import pytest
import logging
from commanduinolabware import CommanduinoLabware
from commanduino.exceptions import CMManagerConfigurationError


@pytest.mark.core
def test_simulation_setting(ramps):

    # Simulation flag should've been set upon fixture creation
    assert ramps._simulation is True


@pytest.mark.core
def test_handlers_parsing(ramps, sensorhub):

    # This only checks that io dict has been found properly in the config
    # To do proper handlers creation testing, simulation has to be implemented in Commanduino itself
    assert ramps.commandhandlers[0]["port"] == "/dev/ttyACM0"
    assert sensorhub.commandhandlers[1]["type"] == "tcpip"
    assert sensorhub.commandhandlers[1]["address"] == "192.168.1.80"
    assert sensorhub.commandhandlers[1]["port"] == "5000"


@pytest.mark.core
def test_merge_io_config_with_params(ramps):

    ios = [{"type":"serial", "port": "COM3"}, {"type": "tcpip", "address": "localhost", "port":"5000"}]
    # No connection mode
    with pytest.raises(CMManagerConfigurationError):
        ramps._merge_io_config_with_params(connection_mode=None, address="localhost", port=5000, ios=ios)
    # No port
    with pytest.raises(CMManagerConfigurationError):
        ramps._merge_io_config_with_params(connection_mode="serial", address="localhost", port=None, ios=ios)
    # TCP/IP with no address
    with pytest.raises(CMManagerConfigurationError):
        ramps._merge_io_config_with_params(connection_mode="tcpip", address=None, port=5000, ios=ios)
    # Add serial connection
    ramps._merge_io_config_with_params(connection_mode="serial", address=None, port="/dev/ttyACM0", ios=ios)
    assert {"type": "serial", "port": "/dev/ttyACM0"} in ios
    # Add TCP connection
    ramps._merge_io_config_with_params(connection_mode="tcpip", address="127.0.0.2", port=5001, ios=ios)
    assert {"type": "tcpip", "address": "127.0.0.2", "port":"5001"} in ios


@pytest.mark.core
def test_singleton(ramps, sensorhub):

    # Test fixtures were created upon test session start
    # They should be references to the same object with combined config
    assert ramps is sensorhub

    # Combined object should have everything from both configs
    for i in range(1, 12):
        assert hasattr(ramps, "mosfet" + str(i))

