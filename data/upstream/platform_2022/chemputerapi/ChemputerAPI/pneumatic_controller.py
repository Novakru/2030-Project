from typing import Union, Optional

from .device import ChemputerDevice
from commanduinolabware import CommanduinoLabware

PRESSURE_LOW = "low"
PRESSURE_HIGH = "high"
STATE_ON = "open"
STATE_OFF = "closed"

class PneumaticController(ChemputerDevice):

    def __init__(self, device_name: str,
                 connection_mode: str,
                 address: Optional[str],
                 port: Union[str, int],
                 simulation: bool = False) -> None:

        # Set up name and logger
        super().__init__(device_name)

        # These should match names of MOSFET control commands defined for
        # the CommandManager in the SensorHub JSON file
        self.outputs = {
            1: ("CH1", "CH2"),
            2: ("CH3", "CH4"),
            3: ("CH5", "CH6"),
            4: ("CH7", "CH8"),
            5: ("CH9", "CH10"),
            6: ("CH11", "CH12")
        }

        # Create configuration for Commanduino
        # IO config
        config = {"ios":[], "devices":{}}
        config["ios"].append({"type": connection_mode,
                              "address": address,
                              "port": str(port)
                             })
        # Devices config
        for output in self.outputs.values():
            for channel in output:
                config["devices"][channel] = {"command_id": channel}
        self.logger.debug("Commanduino config for pneumatic panel: %s", config)

        self.device = CommanduinoLabware(name=self.name,
                                         connection_mode=None,
                                         address=None,
                                         port=None,
                                         config=config,
                                         simulation=simulation)

        self.reset_all_channels()

    def check_channel_number(self, channel: int) -> Optional[int]:
        """Checks that channel number is int and not above 6
        (physical number of channels on the panel)
        """

        channel = int(channel)
        if channel not in range(1, 7):
            self.logger.error("Invalid channel number provided!")
            # FIXME would be nice to throw custom exception but we haven't any.
            # Thus returning None :/
            return None
        return channel

    def switch_vacuum(self, channel: int) -> None:
        """ Connects selected channel to vacuum line.
        """

        channel = self.check_channel_number(channel)
        if channel is not None:
            # MOSFETs are configured for PWM, so write_analog() here
            # Vacuum  - bottom valve On, top valve Off
            self.device.write_analog(self.outputs[channel][0], 255)
            self.device.write_analog(self.outputs[channel][1], 0)

    def switch_argon(self, channel: int, pressure: str = "low") -> None:
        """Connects selected channel to argon line.
        """

        channel = self.check_channel_number(channel)
        if channel is not None:
            # Low pressure - bottom valve Off, top valve Off (default state)
            if pressure == PRESSURE_LOW:
                self.device.write_analog(self.outputs[channel][0], 0)
                self.device.write_analog(self.outputs[channel][1], 0)
            # High pressure - bottom valve Off, top valve On
            elif pressure == PRESSURE_HIGH:
                self.device.write_analog(self.outputs[channel][0], 0)
                self.device.write_analog(self.outputs[channel][1], 255)

    def switch_argon_and_vacuum(self, channel: int, state: str = "closed"):
        """Sets the state for the Argon and Vacuum lines either open or closed

        Args:
            channel (int): Channel to operate on
            state (str, optional): State to set the switch to.
                Defaults to "closed".
        """

        channel = self.check_channel_number(channel)
        if channel is not None:
            if state == STATE_ON:
                self.device.write_analog(self.outputs[channel][0], 255)
                self.device.write_analog(self.outputs[channel][1], 255)
            elif state == STATE_OFF:
                self.device.write_analog(self.outputs[channel][0], 0)
                self.device.write_analog(self.outputs[channel][1], 0)

    def reset_all_channels(self) -> None:
        """ Sets all channels to low pressure argon supply
        """

        for channel in range(1, 7):
            self.switch_argon(channel, pressure=PRESSURE_LOW)
