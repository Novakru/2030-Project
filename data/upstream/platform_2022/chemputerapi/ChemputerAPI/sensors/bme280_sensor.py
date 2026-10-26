"""
Chemputer API for the environment conditions sensor.

The implementation is based on the BME280 sensor connected to the SensorHub
board via i2c switch. See details in the corresponding section of the
Commanduino Library (https://github.com/croningp/commanduino).
"""

from typing import Union, Optional

from commanduinolabware import CommanduinoLabware

from .utils import check_channel
from ..device import ChemputerDevice


class BME280Sensor(ChemputerDevice):
    """ Controller class for the environmental conditions sensor.

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

    def __init__(
            self,
            device_name: str,
            connection_mode: str,
            address: Optional[str],
            port: Union[str, int],
            simulation: bool = False,
            channel: Optional[int] = None,
    ) -> None:

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
            "bme280": {
                "command_id": "BME280" # device name taken from demo.json
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

        if self.channel:
            self.device.i2c_mux_channels_on(self.channel)

    @check_channel
    def get_pressure(self) -> float:
        """ Get the pressure readings.

        Returns:
            Float: pressure in Pascals.
        """

        return self.device.bme280.get_pressure()

    @check_channel
    def get_temperature(self) -> float:
        """ Get the temperature readings.

        Returns:
            Float: temperature in degree Celsius.
        """

        return self.device.bme280.get_temperature()

    @check_channel
    def get_humidity(self) -> float:
        """ Get the humidity readings.

        Returns:
            Float: humidity in %.
        """

        return self.device.bme280.get_humidity()
