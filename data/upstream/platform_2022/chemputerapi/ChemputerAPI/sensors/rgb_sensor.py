"""
Chemputer API for the RGB sensor.

The implementation is based on the TCS34725 sensor connected to the SensorHub
board via i2c switch. See details in the corresponding section of the
Commanduino Library (https://github.com/croningp/commanduino).
"""

import colorsys
from typing import Union, Optional, Dict

from commanduinolabware import CommanduinoLabware

from .utils import check_channel
from ..device import ChemputerDevice

# Found experimentally to increase the range of possible values
# According to the chip datasheet should be [0, 65536] (theoretically!)
DEFAULT_INTEGRATION_TIME = 154
DEFAULT_ANALOG_GAIN = 16


class RGBSensorError(Exception):
    """ Generic sensor error. """

class RGBSensor(ChemputerDevice):
    """ Controller class for the RGB sensor.

    Implementation is based on using the Commanduino Library and connecting the
    sensor via i2c.

    Args:
        connection_mode (str): Connection mode of the SensorHub board.
        address (str, Optional): IP address for the SensorHub board.
        port (Union[str, int]): TCP- or serial port for the SensorHub
            communication.
        simulation (bool): If running in simulation mode.
        channel (int, optional): I2C channel on the SensorHub board. If None,
            assuming the sensor is directly connected to the Arduino, so no
            channel switch is performed.
    """

    # rgb model
    RED = 'red'
    GREEN = 'green'
    BLUE = 'blue'
    CLEAR = 'clear'

    # hsv model
    HUE = 'hue'
    SATURATION = 'saturation'
    VALUE = 'value'

    def __init__(
            self,
            device_name: str,
            connection_mode: str,
            address: Optional[str],
            port: Union[str, int],
            simulation: bool = False,
            channel: Optional[int] = None,
        ) -> None:

        # Set up name and logger
        super().__init__(device_name)

        # configuration for Commanduino
        config = {"ios": [], "devices": {}}
        config["ios"].append(
            {
                "type": connection_mode,
                "address": address,
                "port": str(port),
            }
        )

        # Device config
        config["devices"] = {
            "rgb": {
                "command_id": "TCS"
            }
        }

        # Channel for i2c communication using i2c switch
        # e.g. PCA9548A on SensorHub
        self.channel = channel

        # If channel was given, assuming i2c switch is in use
        # So adding it to devices
        if self.channel is not None:
            config["devices"].update({
                "i2c_mux": {
                    "command_id": "MUX"
                }
            })

        self.device = CommanduinoLabware(
            name=self.name,
            connection_mode=None,
            address=None,
            port=None,
            config=config,
            simulation=simulation
        )

        # initializing the sensor by requesting its initialization code
        self.initialize_sensor()

        # checking device initialization
        if self.device.rgb.initialization_code is not None \
        and self.device.rgb.initialization_code == 0:
            raise RGBSensorError("RGB sensor is not connected!")

        # If initialized successfully, set the default parameters
        self.set_integration_time(DEFAULT_INTEGRATION_TIME)
        self.set_gain(DEFAULT_ANALOG_GAIN)

    @check_channel
    def initialize_sensor(self) -> None:
        """ Initialize the sensor. """

        self.device.rgb.get_initialization_code()

    @check_channel
    def get_rgbc(self) -> Dict[str, int]:
        """ Get the Red, Green, Blue and Clear channels RAW values. """

        red, green, blue, clear = self.device.rgb.get_rgbc()

        return {
            self.RED: red,
            self.GREEN: green,
            self.BLUE: blue,
            self.CLEAR: clear,
        }

    @check_channel
    def get_hsv(self) -> Dict[str, float]:
        """ Get the color values in HSV model. Values are normalized to clear
        channel.
        """

        # normalizing
        red, green, blue, clear = self.device.rgb.get_rgbc()
        try:
            red, green, blue = red/clear, green/clear, blue/clear
        except ZeroDivisionError:
            # if "clear" is 0, no light is coming to the sensor
            red, green, blue = 0, 0, 0

        # converting
        hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)

        return {
            self.HUE: hue,
            self.SATURATION: saturation,
            self.VALUE: value,
        }

    @check_channel
    def set_integration_time(self, integration_time: float) -> None:
        """ Set the integration time.

        Args:
            integration_time (float): Integration time in milliseconds.
            Accepted values: 2.4, 24, 50, 101, 154, 700.
        """

        self.device.rgb.set_integration_time(integration_time)

    @check_channel
    def set_gain(self, gain: int) -> None:
        """ Sets the channels gain.

        Delays the following execution by integration time * gain.

        Args:
            gain (int): Gain for all channels.
                Accepted values: 1, 4, 16, 60.
        """

        self.device.rgb.set_gain(gain)
