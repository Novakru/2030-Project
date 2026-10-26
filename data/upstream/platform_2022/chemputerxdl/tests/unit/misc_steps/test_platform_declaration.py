import pytest
import json
from chemputerxdl import ChemputerPlatform

@pytest.mark.unit
def test_platform_declaration():
    json.dumps(ChemputerPlatform().declaration)
