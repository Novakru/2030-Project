class ChemputerDeviceError(Exception):
    pass


class ConductivitySensorInvalidReadFrequencyError(ChemputerDeviceError):
    def __init__(self, read_frequency, max_possible_read_frequency):
        self.read_frequency = read_frequency
        self.max_possible_read_frequency = max_possible_read_frequency

    def __str__(self):
        return (
            f'Invalid read frequency {self.read_frequency} Hz requested. '
            f'Maximum possible frequency is {self.max_possible_read_frequency}'
            ' Hz due to delays when switching MOSFET on / off.'
        )
