from .constants import VALID_PORTS
import time

class ChempilerError(Exception):
    """Chempiler error base class."""
    pass

class ChempilerInvalidPortError(ChempilerError):
    """Invalid port used for device in graph."""
    def __init__(self, node, node_class, port):
        self.node = node
        self.node_class = node_class
        self.port = port

    def __str__(self):
        valid_ports = []
        if self.node_class in VALID_PORTS:
            valid_ports = VALID_PORTS[self.node_class]
        return f'{self.port} is an invalid port for {self.node} ({self.node_class}).\
 Valid ports: {", ".join([str(port) for port in valid_ports])}'

class ChempilerSensorReadError(ChempilerError):
    """Error reading sensor."""
    pass

class ChempilerStopSensorThreadBeforeStartError(ChempilerSensorReadError):
    """Sensor thread stop requested before sensor thread started."""
    def __str__(self):
        return 'Trying to stop sensor read thread before thread has been\
 started.'

class ChempilerDoubleStartSensorThreadError(ChempilerSensorReadError):
    """Sensor thread start requested while sensor thread is already running."""
    def __str__(self):
        return 'Trying to start thread again that is already running.'

class ChempilerInvalidTempSensorError(ChempilerError):
    """When temp sensor prop not supplied for hotplate or chiller in graph."""
    def __init__(self, node):
        self.node = node

    def __str__(self):
        return f'Invalid `temp_sensor` prop for {self.node}.'
class ChempilerCVError(ChempilerError):
    """Error detected by Chemputer computer vision."""
    def __init__(self):
        pass

class ChempilerBrokenSyringeDetectedError(ChempilerCVError):
    def __init__(self, syringe_breakage_detector):
        self.syringe_breakage_detector = syringe_breakage_detector

    def __str__(self):
        s = 'Computer vision detected syringe breakage. Events:\n'
        for timestamp, template in self.syringe_breakage_detector.events:
            formatted_time = time.strftime(
                '%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
            s += f'    {formatted_time}    {template}\n'
        return s
