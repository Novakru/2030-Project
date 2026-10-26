"""
Provisional API to control the dispensing wheel.
Basically dealing with sending commands like MOTR_1 steps speed
"""
# import socket
# import threading
from .device import ChemputerDevice
# from queue import Queue
# import time
# import logging
from .tools.PoEtree import _TCPEthernetDevice, _SimTCPEthernetDevice

# Hardware specific variables: 
WHEEL_POSITIONS = 5
MOT1_STEPS_PER_ROUND = 200
MOT2_STEPS_PER_ROUND = 200
MICROSTEPPING = 64


########################################################################################################################
#                                                                                                                      #
#       Dispenser classes                                                                                              #
#                                                                                                                      #
########################################################################################################################

class SimDispensingWheel(_SimTCPEthernetDevice, ChemputerDevice):
    """
    Simulation for the dispensig wheel device
    """
    def __init__(self, address, name="", **kwargs):
        _SimTCPEthernetDevice.__init__(self)
        self.logger.info('Received Pump \"{0}\" Address: {1}'.format(name, address))
        self.name = name
        self.steps_mot1 = MOT1_STEPS_PER_ROUND
        self.steps_mot2 = MOT2_STEPS_PER_ROUND
        self.microsteps = MICROSTEPPING
        self.positions = WHEEL_POSITIONS


    def dispense_pos(self, pos, speed_rpm, port=1):#
        self.logger.info(
            f"Dispesning from position {pos} at {speed_rpm} RPM from port\
 {port}.")

    def wait_until_ready(self):
        #TODO logging message and func description
        pass

class DispensingWheel(_TCPEthernetDevice, ChemputerDevice):
    """
    Child class of _TCPEthernetDevice. Gives the user control over the PoEtree boards

    Args:
        address (str): Address of the pump
        name (str): Optional name of the device

    Extends:
        _TCPEthernetDevice
    """
    # dispensing wheel object
    def __init__(self, address, name="", **kwargs):
        _TCPEthernetDevice.__init__(self, address=address, name=name, auto_init=True)
        self.device_type = "dispensing_wheel"
        self.steps_mot = [MOT1_STEPS_PER_ROUND, MOT2_STEPS_PER_ROUND]
        self.microsteps = MICROSTEPPING
        self.positions = WHEEL_POSITIONS
        # COMMAND STRINGS:
        self.motor_sel = "MOTR_"
    
    def dispense_pos(self, pos, speed_rpm, port=1):
        """
        It makes move the wheel a certain number of positions (pos) of the wheel.
        Number of positions the wheel will move (can be also negative).
        The second parameter is the speed in rpm (min: 1, max: 600)
        The third parameter is the motor driver (1 or 2) depeinding on the board used
        """
        steps = int(pos * (self.steps_mot[port - 1] / self.positions)) # steps to be travelled (not microsteps)
        timing = int(60000000/ (speed_rpm * self.microsteps * self.steps_mot[port - 1])) # delay time between each microstep
        self._send_command(self.motor_sel+str(port), steps, timing)
        self.device_ready_flag.wait()

