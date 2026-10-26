"""
.. module:: commanduino_driver
    :platform: Unix, Windows
    :synopsis: Core driver for Commnaduino device Manager

.. moduleauthor:: Graham Keenan (Cronin Lab 2019)

"""

import json
import logging
import time
from typing import Optional, Union, List
from threading import Lock

# Import CommandManager of Commanduino
from commanduino import CommandManager
from commanduino.exceptions import CMManagerConfigurationError

from .exceptions import CMDeviceCommandError


class CommanduinoLabware(CommandManager):
    """A wrapper for interacting with Commanduino devices. Creates proper
    configuration by merging explicit parameters with configuration dictionary,
    creates and instantiates the manager. Provides a number of high-level
    methods for Commanduino devices.
    """

    # Shared state variable
    _instance = None

    @classmethod
    def from_config(cls, conf):
        """
        Obtains the necessary information from a configuration setup.

        Args:
            cls (CommanduinoLabwarer): The instantiating class.

            conf (Dict): Dictionary containing the configuration data.

        """
        sim = conf.get("simulation", False)
        return cls(config=conf, simulation=sim)

    def __new__(cls, *args, **kwargs):
        """ Implements a singleton logic for having one shared
        CommanduinoLabware object.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset(cls):
        """Resets the _instance variable to override singleton logic.
        This is only required in VERY SPECIFIC circumstances and shouldn't
        be used often.
        """

        cls._instance = None

    def __init__(self,
                 name: Optional[str] = None,
                 connection_mode: Optional[str] = None,
                 address: Optional[str] = None,
                 port: Optional[str] = None,
                 config: Optional[Union[str, dict]] = None,
                 simulation: bool = False) -> None:

        # `initialised` attribute gets set to True by CommandManager
        # when it finishes it's __init__(). hasattr() guards against failure
        # on first instantiation of CommanduinoLabware
        if not hasattr(self, "initialised"):
            self.initialised = False

        # If it's first-time object creation set name and logger
        if self.initialised is False:

            # Name of the device
            if name is None:
                name = self.__class__.__name__

            self.name = name
            self.i2c_mux_lock = Lock()

            # Logger object
            self.logger = logging.getLogger(
                __name__ + "." + self.__class__.__name__ + "." + self.name
            )

        # New blank config
        new_config = {"ios": [], "devices": {}}

        # If config passed is dict - load it directly
        if isinstance(config, dict):
            new_config.update(config)

        # Else try load from file
        elif isinstance(config, str):
            try:
                with open(config) as config_file:
                    new_config.update(json.load(config_file))
            except FileNotFoundError:
                raise CMManagerConfigurationError(
                    f"Configuration file {config} not found!")
            except json.JSONDecodeError as e:
                raise CMManagerConfigurationError(
                    f"Can't convert configuration file {config} to JSON! \
                    JSONDecodeError: {e}") from None

        # If we have explicit parameters passed - use them to update
        # configuration dictionary.
        self._merge_io_config_with_params(
            connection_mode, address, port, new_config["ios"]
        )

        # At this point we should have all configuration built properly
        # From combination of the parameters and dictionary passed
        self.logger.debug("Built new configuration: %s", new_config)

        # If it's the first run - instantiate the CommandManager from the config built
        if self.initialised is False:
            # Init manager
            super().__init__(
                command_configs=new_config["ios"],
                devices_dict=new_config["devices"],
                simulation=simulation
            )

        # Otherwise just add extra devices/IOs from new config
        else:
            # Mixing real and simulation devices is not yet supported bc
            # it would likely cause behavioral clusterfuck
            if self._simulation is not simulation:
                raise CMManagerConfigurationError(
                    "Mixing simulated and real devices is not allowed!"
                )

            if new_config["ios"] != []:
                # Add new IOs
                self.logger.info("Adding new IOs...")
                new_ios = new_config["ios"]

                if not self._simulation:
                    active_ios = [h.name for h in self.commandhandlers]
                    for io in new_ios:
                        if io["type"] == "serial":
                            name = io["port"]
                        elif io["type"] == "tcpip":
                            name = io["address"] + ":" + io["port"]
                        if name in active_ios:
                            continue

                        # If name not found - add new CommandHandler
                        self.add_command_handler(io)
                else:
                    self.commandhandlers.extend(new_ios)

            if new_config["devices"] != {}:
                # Add new devices
                # First, check if there are any duplicate names
                self.logger.info("Adding new devices...")
                active_device_names = set(self.devices.keys())
                new_device_names = set(new_config["devices"].keys())
                for dup in active_device_names & new_device_names:
                    self.logger.error(
                        "Duplicate device name %s, device already present!", dup
                    )

                    # Remove duplicate
                    new_config["devices"].pop(dup)

                # Iterate over the rest and add them to manager
                for device_name, device_config in new_config["devices"].items():
                    self.register_device(device_name, device_config)
                # Add found devices as attributes
                for device_name, device_object in self.devices.items():
                    if not hasattr(self, device_name):
                        setattr(self, device_name, device_object)

            self.logger.info("CommanduinoLabware updated.")

    def _merge_io_config_with_params(
        self,
        connection_mode: Optional[str],
        address: Optional[str],
        port: Optional[str],
        ios: List
    ) -> None:
        """Merges the IO configuration dictionary with
        the parameters passed, if any

        Args:
            connection_mode (Optional[str]): Connection mode.
            address (Optional[str]): Connection address.
            port (Optional[str]): Connection port.

        """

        if connection_mode is not None:
            # Port is needed bot for serial and TCP/IP
            if port is None:
                raise CMManagerConfigurationError(f"Explicit {connection_mode}\
 mode requested, but no port provided!")

            # Explicit serial connection
            if port is not None and connection_mode == "serial":
                # Check for duplicates
                if port not in [
                    io["port"] for io in ios if io["type"] == "serial"
                ]:
                    ios.append({"port": str(port), "type": "serial"})
                    self.logger.info(
                        "Appended %s(%s) from parameters", port, connection_mode
                    )

            # Explicit TCP/IP connection
            elif port is not None and connection_mode == "tcpip":
                port = str(port)
                if address is None:
                    raise CMManagerConfigurationError("Explicit TCP/IP mode\
 requested, but no address provided!")

                # Check for duplicates
                # Use crude address+port as connection id
                if address + port not in [
                    io["address"] + io["port"]
                    for io in ios if io["type"] == "tcpip"
                ]:
                    ios.append({
                        "port": str(port), "address": address, "type": "tcpip"
                    })

                    self.logger.info(
                        "Appended %s:%s(%s) from parameters",
                        address, port, connection_mode
                    )

        elif port is not None or address is not None:
            raise CMManagerConfigurationError(
                "Address/port provided with no connection mode!"
            )

    def valid_device(self, device_name: str) -> bool:
        """Checks if a supplied device is present in the devices dictionary

        Args:
            device_name (str): Name of the device to check for

        Returns:
            bool: Present in device dictionary or not
        """

        # Not there, log and return
        if device_name not in self.devices:
            self.logger.warning(
                'Device %s not present in CommandDevice dictionary!',
                device_name
            )
            return False

        return True

    def write_digital(self, pin: str, level: int = 0) -> None:
        """Sets a digital pin to the HIGH or LOW state, dependent on level

        Args:
            pin (str): Name of the pin in the CommandManager
            level (int, optional): Level to set, always 0 or 1. Defaults to 0.
        """

        if not self.valid_device(pin):
            return

        # Everything except 0 would be HIGH, 0 would be LOW
        self.logger.debug("Setting digital pin %s to level %s", pin, level)
        self.devices[pin].set_level(level)

    def write_analog(self, pin: str, value: int = 0) -> None:
        """Sets the PWM value of an analog pin. Between 0 and 255

        Args:
            pin (str): Name of the pin in the CommandManger
            value (int, optional): PWM value between 0 and 255. Defaults to 0.
        """

        if not self.valid_device(pin):
            return

        # PWM values less than 0 default to 0 and values above 255 go to 255.
        self.logger.debug("Setting PWM on analog pin %s to %s", pin, value)
        self.devices[pin].set_pwm_value(value)

    def read_digital(self, pin: str) -> int:
        """Reads the current state of a digital pin. HIGH or LOW.

        Args:
            pin (str): name of the pin in the CommandManager

        Returns:
            int: Current state of the pin HIGH (1) or LOW (0)
        """

        if not self.valid_device(pin):
            return

        state = self.devices[pin].get_state()
        self.logger.debug("Read value of digital pin %s = %s", pin, state)
        return state

    def read_analog(self, pin: str) -> int:
        """Reads the current PWM value of an analog pin. Between 0 and 255

        Args:
            pin (str): Name of the pin in the CommandManager

        Returns:
            int: Current PWM value of the pin. Between 0 and 255
        """

        value = self.devices[pin].get_level()
        self.logger.debug("Read PWM of value analog pin %s = %s", pin, value)
        return value

    def turn_motor(
        self,
        motor: str,
        n_turns: int = 1,
        increment: int = 6400,
        wait: bool = True
    ) -> None:
        """Turn the motor a full 360 degrees
        Used for the Geneva Wheel mechanism.
        Assumes the use of a Nema17 motor.

        Args:
            motor (str): Name of the motor given in the config
            n_turns (int, optional): Number of turns to perform. Defaults to 1.
            increment (int, optional): Increment steps. Defaults to 6400.
            wait (bool, optional): Wait for operation to complete.
                                    Defaults to True.
        """

        if not self.valid_device(motor):
            return

        # Move a full turn for n_turn times
        self.logger.debug("Turning motor %s %s times.", motor, n_turns)
        for _ in range(n_turns):
            self.devices[motor].move(increment, wait=wait)

        # Reset motor position in case of overflow if running for extended
        # period of time.
        self.devices[motor].set_current_position(0)

    def move_motor(self, motor: str, steps: int, wait: bool = True) -> None:
        """Moves a motor a number of steps.
        Moves in the direction given in the config

        Note:
            The motor is prone to integer overflow if incremented too far.
            This means the motor may unexpectedly turn the other direction

        Args:
            motor (str): Name of the motor given in the config
            steps (int): Number of steps to move
            wait (bool, optional): Wait for operation to complete.
                                    Defaults to True.
        """

        if not self.valid_device(motor):
            return

        # Move a given number of steps
        self.logger.debug("Moving motor %s %s steps.", motor, steps)
        self.devices[motor].move(steps, wait=wait)

    def move_motor_to_position(
        self,
        motor: str,
        position: int,
        wait: bool = True
    ) -> None:
        """Moves a motor to a given position, in steps
        Motor moves to a static position relative to its current position

        Args:
            motor (str): Name of the motor given in the config
            position (int): Position to move to
            wait (bool, optional): Wait for the operation to complete.
                                    Defaults to True.
        """

        if not self.valid_device(motor):
            return

        # Move the motor to the given position
        self.logger.debug("Moving motor %s to position %s", motor, position)
        self.devices[motor].move_to(position, wait=wait)

    def home_motor(self, motor: str, wait: bool = True) -> None:
        """Moves a motor to its home position.
        Requires a home switch to be present.

        Note:
            If no home switch is present for the motor, this runs indefinitely

        Args:
            motor (str): Name of the motor
            wait (bool, optional): Wait for the operation to complete.
                                    Defaults to True.
        """

        if not self.valid_device(motor):
            return

        # Move to home position
        self.logger.debug("Homing motor %s.", motor)
        self.devices[motor].home(wait=wait)

    def run_motor(
        self, motor: str, duration: int, increment: int = 8000
    ) -> None:
        """Runs a motor for a given period of time, in seconds.

        Args:
            motor (str): Name of the motor
            duration (int): Length of time to run for, in seconds
            increment (int, optional): Increment in steps. Defaults to 8000.
        """

        if not self.valid_device(motor):
            return

        # Get the current time
        current_time = time.time()

        # Move a given number of steps until time has elapsed
        self.logger.debug("Running motor %s for %s seconds.", motor, duration)
        while time.time() < (current_time + duration):
            self.devices[motor].move(increment)

    def reverse_motor_direction(self, motor: str) -> None:
        """Reverses the direction of the motor movement

        Args:
            motor (str): Name of the motor
        """

        if not self.valid_device(motor):
            return

        self.devices[motor].reverted_direction = (
            not self.devices[motor].reverted_direction
        )

    def set_motor_speed(self, motor: str, speed: int) -> None:
        """Sets the speed of a motor

        Args:
            motor (str): Name of the motor
            speed (int): Speed of the motor
        """

        if not self.valid_device(motor):
            return

        self.logger.debug("Setting motor %s speed to %s", motor, speed)
        self.devices[motor].set_max_speed(speed)
        self.devices[motor].set_running_speed(speed)

    def set_i2c_mux_name(self, name: str) -> None:
        """ Stores a provided name as an internal attribute for PCA9548A device.
        This is needed if the name has been redefined in Commanduino
        configuration from the default "i2c_mux" for any reason in order for the
        functions below to work
        """

        if hasattr(self, "i2c_mux"):
            self.logger.warning("'i2c_mux' attribute already present!")
            return None
        self.i2c_mux = self.devices[name]

    def i2c_mux_channels_on(self, *channels: List[int]) -> None:
        """Connects selected I2C channels on the MUX.
        Status of the other channels is preserved.
        This is a wrapper to provide alternate syntax for get_i2c_channels().

        Args:
            *channels: List of channels (e.g [1,3,5]) to disconnect
        """
        self._switch_pca9548a_channels(channels, on=True)

    def i2c_mux_channels_off(self, *channels: List[int]) -> None:
        """Disconnects selected I2C channels on the MUX.
        Status of the other channels is preserved.
        This is a wrapper to provide alternate syntax for get_i2c_channels().

        Args:
            *channels: List of channels (e.g [1,3,5]) to disconnect
        """
        self._switch_pca9548a_channels(channels, on=False)

    def set_i2c_mux_channels(self, *channels: List[int]) -> None:
        """Sets the state of all I2C channels on the PCA9548A mux.
        This is a method that triggers respective Commanduino method.
        If an arguments is not supplied for the channel, it would be
        switched off.
        Thus, set_i2c_channels(0) will switch off all channels.

        Args:
            *channels: List of channel states (e.g [1,0,0,1]) where index
                        represents channel number, 0/1 - channel state.
        """

        self.i2c_mux.set_channels(self._pca9548a_list_to_mask(channels))

    def get_i2c_mux_channels(self) -> List[int]:
        """Gets the current state of channels on the PCA9548A mux.
        This is a method that triggers respective Commanduino method.


        Returns:
            List[int]: List of channel states (e.g [1,0,0,1]) where index
            represents channel number, 0/1 - channel state.
        """

        # This monkey-patching is ugly, but necessary,
        # as the Commanduino itself doesn't have the simulation mode,
        # and other functions here need some sensible value returned.

        mask = self.i2c_mux.get_channels() if not self._simulation else 42
        return self._pca9548a_mask_to_list(mask)

    def _switch_pca9548a_channels(
        self, channels: List[int], on: bool = False
    ) -> None:
        """Connects/disconnects selected I2C channels on the MUX.
        Status of the other channels is preserved.
        Channel numbering starts from 1.

        Args:
            *channels: List of channels (e.g [1,3,5]) to connect/disconnect
            on: True - connect channels, False - disconnect channels
        """

        # Filter off duplicates
        channels = list(set(channels))
        # Check if any element is bigger that 8 and spit a warning
        # And that we have numbering starting from 1, i.e. no zero channel

        for c in channels.copy():
            if c > 8:
                self.logger.warning(
                    "Channel number %s higher that allowed %s, removing.", c, 8
                )
                channels.remove(c)

            if c == 0:
                self.logger.warning(
                    "Channel number 0 is not allowed, removing."
                )
                channels.remove(c)

        # If after filtering we have empty channel list - nothing to do
        if channels == []:
            self.logger.warning("Empty channel list!")
            return

        # Initialize empty bit list
        channels_required = [0] * 8
        for c in channels:
            channels_required[c - 1] = 1

        self.logger.debug(
            "_switch_i2c_channels()::filtered channels list %s",
            channels_required
        )

        # Construct mask
        mask_required = self._pca9548a_list_to_mask(channels_required)

        # Get current channels state mask
        mask_current = (
            self.i2c_mux.get_channels() if not self._simulation else 42
        )

        if on is True:
            # OR
            self.logger.debug(
                "_switch_i2c_channels()::%s OR %s",
                format(mask_current, "#010b"),
                format(mask_required, "#010b")
            )
            mask_required = mask_current | mask_required  # Switching OAN

        else:
            # AND NOT
            self.logger.debug(
                "_switch_i2c_channels()::%s AND NOT %s",
                format(mask_current, "#010b"),
                format(mask_required, "#010b")
            )
            mask_required = mask_current & ~mask_required  # Switching AFF!

        self.logger.debug(
            "_switch_i2c_channels()::resulting mask %s",
            format(mask_required, "#010b")
        )

        # Write back
        self.i2c_mux.set_channels(mask_required)

    def _pca9548a_mask_to_list(self, mask: int) -> List[int]:
        """Converts one byte mask into a list of individual bits.
        E.g. 27 -> [1, 1, 0, 1, 1, 0, 0, 0]
        Note that the mask gets inverted bc PCA9548A accepts CH8 as MSB.

        Args:
            mask (int): Bitmask in int

        Returns:
            List[int]: List of individual bits
        """
        # Check that we are not overflowing
        if mask > 255:
            raise CMDeviceCommandError(
                f"Calculated channel mask {mask}, invalid configuration!"
            )

        # Get active channels mask as an int
        # And convert to eight-bit padded binary string("0b00000000")
        lst = format(int(mask), "#010b")
        # Chop off "0b" prefix
        lst = lst[2:]
        # Split to list of integers
        lst = [int(i) for i in lst]
        lst.reverse()
        return lst

    def _pca9548a_list_to_mask(self, channels: List[int]) -> int:
        """Converts a list of individual bits into one byte mask
        E.g. [1, 1, 0, 1, 1, 0, 0, 0] -> 27
        Note that the mask gets inverted bc PCA9548A accepts CH8 as MSB.

        Args:
            channels (List[int]): List of individual bits

        Returns:
            (int): Bitmask in int
        """

        # Check each value is 0 or 1
        lst = []
        for value in channels:
            if value in (0, 1):
                lst.append(value)
            else:
                self.logger.warning(
                    "Incorrect value %s found in the channels state list,\
 setting to 0.", value)

                lst.append(0)

        # Check arguments list length
        if len(lst) > 8:
            self.logger.warning("Channel list too long, it will be truncated")
            lst = lst[:8]

        lst.reverse()
        self.logger.debug("_list_to_mask()::final bit list - %s", lst)

        # Convert to binary string
        mask = "".join([str(c) for c in lst])
        self.logger.debug("_list_to_mask()::mask - %s", mask)
        # Then to int and voila
        return int(mask, 2)
