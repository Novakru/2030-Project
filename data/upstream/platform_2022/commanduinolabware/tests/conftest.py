import pytest
import commanduinolabware


@pytest.fixture(scope="session")
def ramps():
    configfile = "./commanduinolabware/boards/ramps/config.json"
    return commanduinolabware.CommanduinoLabware.from_configfile(configfile)

@pytest.fixture(scope="session")
def sensorhub():
    configfile = "./commanduinolabware/boards/sensorhub/config_full.json"
    return commanduinolabware.CommanduinoLabware.from_configfile(configfile)
