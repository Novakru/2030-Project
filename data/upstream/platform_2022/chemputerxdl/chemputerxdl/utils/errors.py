from xdl.errors import XDLCompilationError
from ..constants import VALID_TEMPERATURE_SENSORS

class XDLInvalidTempSensorError(XDLCompilationError):
    def __init__(self, sensor: str):
        self.sensor = sensor

    def __str__(self):
        valid_sensors = ', '.join([k for k in VALID_TEMPERATURE_SENSORS])
        return (
            'Received an invalid sensor definition. '
            f'Valid sensor values are {valid_sensors}. '
            f'Received {self.sensor} instead.'
        )
