"""
(c) 2019 The Cronin Group, University of Glasgow

This class provides all real-life applications of hotplate stirrers within the
Chemputer rig, essentially
just wrapping the original class methods.
"""

import logging
import time
from time import sleep

from chempiler.tools.constants import COOLING_THRESHOLD
from SerialLabware.controllers import (
    AbstractStirringController, AbstractHotplate)


class StirrerExecutioner(object):
    """
    Class to interface with Stirrer plates

    TODO: add try/except statements to catch calls to unsupported methods!
    """
    def __init__(self, graph, simulation):
        """
        Initialiser for the StirrerExecutioner class

        Args:
            graph (DiGraph): Graph representing the platform
            simulation (bool): Simulation mode
        """
        self.graph = graph
        self.simulation = simulation
        self.logger = logging.getLogger(
            "main_logger.stirrer_executioner_logger")

    def _get_stirrer_object(self, node_name):
        """
        Iterates over the graph and looks for the stirrer attached to the node
        passed as argument.
        NOTA BENE: If more than one stirrer is attached to one node, one of them
        is returned, with no guarantee which one.

        Args:
            node_name (str): Name of a node in the graph

        Returns:
            SerialLabware object representing the stirrer attached to the node.

        Raises:
            KeyError: An error if no stirrer is found.
        """
        if node_name in self.graph.nodes():
            for attached_node in self.graph.predecessors(node_name):
                node_object = self.graph.obj(attached_node)

                # SL2 Compatible stirrer detection. Patch by Dario Cambie
                if isinstance(node_object, AbstractStirringController):
                    return node_object

            raise KeyError(
                "ERROR: node {0} has no recognised stirrer attached!".format(
                    node_name))
        else:
            raise KeyError("ERROR: node {0} is not recognised!".format(
                node_name))

    def _get_heater_object(self, node_name):
        """
        Iterates over the graph and looks for the heater attached to the node
        passed as argument. NOTA BENE: If more than one heater is attached to
        one node, one of them is returned, with no guarantee which one.

        Args:
            node_name (str): Name of a node in the graph

        Returns:
            SerialLabware object representing the heater attached to the node.

        Raises:
            KeyError: An error if no heater is found.
        """
        if node_name in self.graph.nodes():
            for attached_node in self.graph.predecessors(node_name):
                node_object = self.graph.obj(attached_node)
                if isinstance(node_object, AbstractHotplate):
                    return node_object

            raise KeyError(
                "ERROR: node {0} has no recognised heater attached!".format(
                    node_name))
        else:
            raise KeyError(
                "ERROR: node {0} is not recognised!".format(node_name))

    def stir(self, node_name):
        """
        Starts the stirring the stirrer plate

        Args:
            node_name (str): Name of the stirrer
        """
        self.logger.info(
            "Starting stirring for hotplate {0}...".format(node_name))
        stirrer_obj = self._get_stirrer_object(node_name)
        self.graph.acquire(stirrer_obj.device_name)

        stirrer_obj.start_stirring()
        self.logger.info("Done.")

        self.graph.release(stirrer_obj.device_name)

    def heat(self, node_name):
        """
        Starts heating the stirrer plate

        Args:
            node_name (str): Name of the stirrer
        """
        self.logger.info(
            "Starting heating for hotplate {0}...".format(node_name))
        heater_obj = self._get_heater_object(node_name)
        self.graph.acquire(heater_obj.device_name)

        heater_obj.start_temperature_regulation()
        self.logger.info("Done.")

        self.graph.release(heater_obj.device_name)

    def wait_for_temp(
        self,
        node_name,
        final_stage_timeout: int = 600,
        relaxed_cooling_threshold: int = 5,
    ):
        """
        Waits for the stirrer to reach its setpoint temperature (approaching
        from either way)

        Args:
            node_name (str): Name of the stirrer
            relaxed_cooling_threshold (float): Acceptable if temp within this
                range. Still try to get to target temp but give up after
                final_stage_timeout has elapsed since reaching within this
                threshold. Only applies when going to RT.
            final_stage_timeout (float): Time to wait after
                relaxed_cooling_threshold has been reached before giving up and
                continuing. Only applies when going to RT.
        """
        heater_obj = self._get_heater_object(node_name)
        sensor_name, sensor_code = self.graph.get_temp_sensor(heater_obj.name)

        if self.simulation:
            self.logger.info("Waiting for temperature using"
                             f"{sensor_name} sensor... Done.")
        else:
            near_target_start_t = 0
            self.graph.acquire(heater_obj.device_name)

            while True:
                try:
                    setpointfloat = heater_obj.get_temperature_setpoint()
                    start_temp = heater_obj.get_temperature(sensor_code)
                    break
                except Exception:
                    continue
            self.logger.info(
                f"Heater {node_name} waiting to reach {setpointfloat} °C"
                f"using {sensor_name} sensor..."
            )
            if start_temp < setpointfloat:  # approach from below
                while True:
                    try:
                        current_temp = heater_obj.get_temperature(sensor_code)
                        # Check if target temp reached.
                        if current_temp > (setpointfloat - COOLING_THRESHOLD):
                            break

                        # If setpoint is RT
                        if 18 <= setpointfloat <= 25:

                            # If acceptable value near target temp reached.
                            if (current_temp
                                    > (setpointfloat
                                       - relaxed_cooling_threshold)):

                                # If this is the first time the near point has
                                # been reached start clock.
                                if not near_target_start_t:
                                    near_target_temp_start_t = time.time()

                                # If near temp has been reached for greater than
                                # timeout value, break.
                                elif (time.time() - near_target_temp_start_t
                                        > final_stage_timeout):
                                    break

                        else:
                            self.logger.info(
                                "Still heating..."
                                f"Current temperature: {current_temp} °C"
                                f" using {sensor_name} sensor"
                            )
                            sleep(5)
                    except Exception:
                        continue
            elif start_temp > setpointfloat:  # approach from above
                while True:
                    try:
                        current_temp = heater_obj.get_temperature(sensor_code)
                        if current_temp < (setpointfloat + COOLING_THRESHOLD):
                            break

                        # If setpoint is RT.
                        if 18 <= setpointfloat <= 25:

                            # If acceptable value near target temp reached.
                            if (current_temp
                                    < (setpointfloat
                                       + relaxed_cooling_threshold)):

                                # If this is the first time the near point has
                                # been reached start clock.
                                if not near_target_start_t:
                                    near_target_start_t = time.time()

                                # If near temp has been reached for greater than
                                # timeout value, break.
                                elif (time.time() - near_target_start_t
                                        > final_stage_timeout):
                                    break

                        else:
                            self.logger.info(
                                "Still cooling... Current temperature: "
                                f"{current_temp} °C using {sensor_name} sensor"
                            )
                            sleep(5)
                    except Exception:
                        continue

            self.graph.release(heater_obj.device_name)

    def stop_stir(self, node_name):
        """
        Stops stirring the stirrer plate

        Args:
            node_name (str): Name of the stirrer
        """
        self.logger.info(
            "Stopping stirring for hotplate {0}...".format(node_name))
        stirrer_obj = self._get_stirrer_object(node_name)
        self.graph.acquire(stirrer_obj.device_name)

        stirrer_obj.stop_stirring()
        self.logger.info("Done.")

        self.graph.release(stirrer_obj.device_name)

    def stop_heat(self, node_name):
        """
        Stops heating the stirrer plate

        Args:
            node_name (str): Name of the stirrer
        """
        self.logger.info(
            "Stopping heating for hotplate {0}...".format(node_name))
        heater_obj = self._get_heater_object(node_name)
        self.graph.acquire(heater_obj.device_name)

        heater_obj.stop_temperature_regulation()
        self.logger.info("Done.")

        self.graph.release(heater_obj.device_name)

    def set_temp(self, node_name, temp):
        """
        Sets the temperature of the stirrer plate

        Args:
            node_name (str): Name of the stirrer
            temp (float): Temperature to set
        """
        heater_obj = self._get_heater_object(node_name)
        sensor_name, sensor_code = self.graph.get_temp_sensor(
            heater_obj.device_name)
        self.logger.info(
            f'Setting temperature for hotplate {node_name} to {temp} °C'
            f'using {sensor_name} probe...'
        )
        self.graph.acquire(heater_obj.device_name)

        heater_obj.set_temperature(temp, sensor_code)
        self.logger.info("Done.")

        self.graph.release(heater_obj.device_name)

    def set_stir_rate(self, node_name, stir_rate):
        """
        Sets the stirring rate of the stirrer

        Args:
            node_name (str): Name of the stirrer
            stir_rate (int): Stirring rate to set
        """
        self.logger.info(
            "Setting stir rate for hotplate {0} to {1} RPM...".format(
                node_name, stir_rate))
        stirrer_obj = self._get_stirrer_object(node_name)
        self.graph.acquire(stirrer_obj.device_name)

        stirrer_obj.set_speed(stir_rate)
        self.logger.info("Done.")

        self.graph.release(stirrer_obj.device_name)
