"""
(c) 2019 The Cronin Group, University of Glasgow

This class provides all real-life applications of recirculation chillers within
the Chemputer rig, essentially just wrapping the original class methods.
"""

import logging
from time import sleep
import time

from chempiler.tools.constants import COOLING_THRESHOLD
from ..errors import ChempilerError
from ..constants import CHILLER_CLASSES


class ChillerExecutioner(object):
    """
    Class for interfacing with the Chiller objects
    """
    def __init__(self, graph, simulation):
        """
        Initialiser for the ChillerExecutioner class

        Args:
            graph (DiGraph): Graph representing the platform
            simulation (bool): Simulation mode
        """
        self.graph = graph
        self.simulation = simulation
        self.logger = logging.getLogger(
            "main_logger.chiller_executioner_logger")

    def _get_chiller_object(self, node_name):
        """
        Iterates over the graph and looks for the chiller attached to the node
        passed as argument. NOTA BENE: If more than one chiller is attached to
        one node, one of them is returned, with no guarantee which one.

        Args:
            node_name (str): Name of a node in the graph

        Returns:
            SerialDevice: SerialLabware object representing the chiller attached
                          to the node.

        Raises:
            KeyError: An error if no chiller is found.
        """

        if node_name in self.graph.nodes:
            for node in self.graph.predecessors(node_name):
                node_object = self.graph.obj(node)
                if node_object.__class__.__name__ in CHILLER_CLASSES:
                    return node_object
            raise KeyError(
                "ERROR: node {0} has no recognised chiller attached!".format(
                    node_name))
        else:
            raise KeyError(
                "ERROR: node {0} is not recognised!".format(node_name))

    def start_chiller(self, node_name):
        """
        Starts the circulation and heating/cooling action

        Args:
            node_name (str): Name of the chiller
        """
        self.logger.info("Starting chiller {0}...".format(node_name))
        chiller_obj = self._get_chiller_object(node_name)
        self.graph.acquire(chiller_obj.device_name)

        chiller_obj.start()
        self.logger.info("Done.")

        self.graph.release(chiller_obj.device_name)

    def stop_chiller(self, node_name):
        """
        Stops the circulation and heating/cooling action

        Args:
            node_name (str): Name of the chiller
        """
        self.logger.info("Stopping chiller {0}...".format(node_name))
        chiller_obj = self._get_chiller_object(node_name)
        self.graph.acquire(chiller_obj.device_name)

        chiller_obj.stop()
        self.logger.info("Done.")

        self.graph.release(chiller_obj.device_name)

    def set_temp(self, node_name, temp):
        """
        Sets the temperature of the chiller

        Args:
            node_name (str): Name of the chiller
            temp (float): Temperature to set
        """
        chiller_obj = self._get_chiller_object(node_name)
        sensor_name, sensor_code = self.graph.get_temp_sensor(
            chiller_obj.device_name)

        self.logger.info(
            f'Setting temperature for chiller {node_name} to {temp} °C '
            f'using {sensor_name} probe.'
        )
        self.graph.acquire(chiller_obj.device_name)

        chiller_obj.set_temperature(temp, sensor_code)
        self.logger.info("Done.")

        self.graph.release(chiller_obj.device_name)

    def cooling_power(self, node_name, cooling_power):  # TODO check if CF41
        """
        Sets the cooling power of the chiller. Only works with Julabo CF41.

        Args:
            node_name (str): Name of the chiller
            cooling_power (int): Cooling power in % (range 0..100)
        """
        self.logger.info(
            "Setting cooling power for chiller {0} to {1}%...".format(
                node_name, cooling_power))
        chiller_obj = self._get_chiller_object(node_name)
        self.graph.acquire(chiller_obj.device_name)

        # Check chiller_obj has `set_cooling_power` method
        if hasattr(chiller_obj, 'set_cooling_power'):
            chiller_obj.set_cooling_power(cooling_power=cooling_power)
        else:
            self.graph.release(chiller_obj.device_name)
            raise ChempilerError(
                f'Chiller "{node_name}" has no method `set_cooling_power`')
        self.logger.info("Done.")

        self.graph.release(chiller_obj.device_name)

    # This doesn't work for all chillers
    def ramp_chiller(self, node_name, ramp_duration, temp):
        """
        Sets the ramp duration and the end temperature for the chiller

        Args:
            node_name (str): Name of the chiller
            ramp_duration (int): Duration of the ramp in sec
            temp (float): End temperature to ramp to in °C
        """
        self.logger.warning("This may fail depending on your type of Chiller!")
        self.logger.info(
            "Chiller {0}: Setting ramp duration to {1}s and temperature to\
 {2}°C...".format(node_name, ramp_duration, temp))
        chiller_obj = self._get_chiller_object(node_name)
        self.graph.acquire(chiller_obj.device_name)

        if hasattr(chiller_obj, 'ramp_temperature'):
            chiller_obj.ramp_temperature(temp, ramp_duration)
        else:
            self.graph.release(chiller_obj.device_name)
            raise ChempilerError(
                f'Chiller "{node_name}" has no method `set_cooling_power`')
        self.logger.info("Done.")

        self.graph.release(chiller_obj.device_name)

    def wait_for_temp(
        self,
        node_name: str,
        relaxed_cooling_threshold: float = 5,
        final_stage_timeout: float = 600,
    ):
        """
        Waits for the chiller to reach its setpoint temperature (approaching
        from either way)

        Args:
            node_name (str): Name of the chiller
            relaxed_cooling_threshold (float): Acceptable if temp within this
                range. Still try to get to target temp but give up after
                final_stage_timeout has elapsed since reaching within this
                threshold. Only applies when going to RT.
            final_stage_timeout (float): Time to wait after
                relaxed_cooling_threshold has been reached before giving up and
                continuing. Only applies when going to RT.
        """
        chiller_obj = self._get_chiller_object(node_name)
        sensor_name, sensor_code = self.graph.get_temp_sensor(
            chiller_obj.device_name)

        if self.simulation:
            self.logger.info(
                f"Waiting for temperature using sensor {sensor_name}... Done.")
        else:
            near_target_start_t = 0
            sensor_name, sensor_code = self.graph.get_temp_sensor(node_name)
            self.graph.acquire(chiller_obj.device_name)

            setpoint = chiller_obj.get_temperature_setpoint()
            self.logger.info(f"Chiller {node_name} waiting to reach "
                             f"{setpoint} °C at {sensor_name} sensor...")
            if chiller_obj.get_temperature(sensor_code) < setpoint:
                # approach from below
                while (abs(chiller_obj.get_temperature(sensor_code) - setpoint)
                       > COOLING_THRESHOLD):

                    # If setpoint is RT
                    if 18 <= setpoint <= 25:

                        # If acceptable value RT reached.
                        if (chiller_obj.get_temperature(sensor_code)
                                > setpoint - relaxed_cooling_threshold):

                            # If this is the first time the near point has been
                            # reached start clock.
                            if not near_target_start_t:
                                near_target_start_t = time.time()

                            # If near temp has been reached for greater than
                            # timeout value, break.
                            elif (time.time() - near_target_start_t
                                    > final_stage_timeout):
                                break

                    self.logger.info(
                        "Still heating... Current temperature: {0}°C".format(
                            chiller_obj.get_temperature(sensor_code)))
                    sleep(5)
            # approach from above
            elif chiller_obj.get_temperature(sensor_code) > setpoint:
                while (abs(chiller_obj.get_temperature(sensor_code) - setpoint)
                       > COOLING_THRESHOLD):

                    # If setpoint is RT
                    if 18 <= setpoint <= 25:

                        # If acceptable value near target temp reached.
                        if (chiller_obj.get_temperature(sensor_code)
                                < setpoint + relaxed_cooling_threshold):

                            # If this is the first time the near point has been
                            # reached start clock.
                            if not near_target_start_t:
                                near_target_start_t = time.time()

                            # If near temp has been reached for greater than
                            # timeout value, break.
                            elif (time.time() - near_target_start_t
                                    > final_stage_timeout):
                                break

                    self.logger.info(
                        "Still cooling... Current temperature: {0}°C".format(
                            chiller_obj.get_temperature(sensor_code)))
                    sleep(5)

            self.graph.release(chiller_obj.device_name)
