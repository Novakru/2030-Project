"""
Chemputer API for controlling Optek Tube Liquid Sensor OPB350, using the
SensorHub board.
"""

from typing import Union, Optional

from commanduinolabware import CommanduinoLabware

from ..device import ChemputerDevice


class BubbleSensor(ChemputerDevice):
    """ Controller class for the OPB350 tube bubble sensor.

    Assuming using the SensorHub.

    Args:
        connection_mode (str): Connection mode of the SensorHub board.
        address (str, Optional): IP address for the SensorHub board.
        port (Union[str, int]): TCP- or serial port for the SensorHub
            communication.
        simulation (bool): If running in simulation mode.
        analog_pin (int): Analog pin, where the sensor is plugged.
    """

    def __init__(self, device_name: str,
                 connection_mode: str,
                 address: Optional[str],
                 port: Union[str, int],
                 analog_pin: int = 2, # as 1 defaults to ConductivitySensor
                 simulation: bool = False) -> None:

        # Set up name and logger
        super().__init__(device_name)

        # SNAR and SNSW are the commands to read from analog channel N
        # and toggle digital channel N on the sensorhub (ADC IN connector).

        # FIXME There's currently a bug in commanduino that wouldn't allow to
        # use all 8 channels simultaneously if that is needed.
        # See https://github.com/croningp/Arduino-CommandHandler/pull/1
        self.sensor_pin = f'S{analog_pin}AR'
        self.digital_pin = f'S{analog_pin}DW'

        # Create configuration for Commanduino
        # IO config
        config = {"ios":[], "devices":{}}
        config["ios"].append({"type": connection_mode,
                              "address": address,
                              "port": str(port)
                             })
        # Devices config
        config["devices"] = {self.sensor_pin: {"command_id": self.sensor_pin},
                             self.digital_pin: {"command_id": self.digital_pin}
                            }
        self.logger.debug("Commanduino config for pneumatic panel: %s", config)

        self.device = CommanduinoLabware(name=self.name,
                                         connection_mode=None,
                                         address=None,
                                         port=None,
                                         config=config,
                                         simulation=simulation)

    def take_reading(self):
        """ Takes reading (default).
        """
        return self.device.read_analog(self.sensor_pin)
