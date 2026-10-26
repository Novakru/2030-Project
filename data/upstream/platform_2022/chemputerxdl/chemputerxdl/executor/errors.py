from typing import Union

# XDL
from xdl.errors import XDLCompilationError
from xdl.steps import Step

# Relative
from ..constants import VALID_PORTS

class XDLNoSolventsError(XDLCompilationError):
    pass

class XDLNoneVesselError(XDLCompilationError):
    def __init__(self, step: Step, prop: str) -> None:
        self.step = step
        self.prop = prop

    def __str__(self):
        return f'{self.step.name} {self.prop} is None'

class XDLNotEnoughBufferFlasksError(XDLCompilationError):
    def __init__(
        self, n_buffer_flasks_required: int, n_buffer_flasks_present: int
    ) -> None:
        self.n_buffer_flasks_present = n_buffer_flasks_present
        self.n_buffer_flasks_required = n_buffer_flasks_required

    def __str__(self):
        return f'The procedure requires {self.n_buffer_flasks_required} empty\
 buffer flasks but only {self.n_buffer_flasks_present} are present in the\
 graph.'

class XDLInvalidPortError(XDLCompilationError):
    def __init__(
        self, vessel: str, vessel_class: str, port: Union[str, int]
    ) -> None:
        self.vessel = vessel
        self.vessel_class = vessel_class
        self.port = port

    def __str__(self):
        return f'{self.port} is an invalid port for {self.vessel}.\
 Valid ports: {", ".join(VALID_PORTS[self.vessel_class])}'

class XDLInsufficientHardwareError(XDLCompilationError):
    def __init__(self, vessel_type, n_required, n_present):
        self.vessel_type = vessel_type
        self.n_required = n_required
        self.n_present = n_present

    def __str__(self):
        return f'{self.n_required} {self.vessel_type}s required,\
 {self.n_present} found in graph.'
