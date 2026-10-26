"""
(c) 2019 The Cronin Group, University of Glasgow

This class provides a number of higher-level convenience functions that are
useful in organic chemical synthesis. Notably, it exposes the `separate_phases`
function, which is a fairly robust phase separation procedure based on
conductivtiy measurements, currently tied to `SerialLabware.ConductivitySensor`.
"""
from typing import Callable, List, Union, Tuple, Dict, Any, Sequence
import logging
import json
import time
import copy
import math
import statistics

from networkx import MultiDiGraph

from .. import constants
from ..errors import ChempilerError, ChempilerInvalidPortError
from ..graph import ChempilerPathStep

class PumpExecutioner(object):

    """
    Executes the Pump movements around the platform_server
    """

    def __init__(
        self, graph: MultiDiGraph,
        simulation: bool,
        crash_dump: str,
    ) -> None:
        """
        Initialiser for the PumpExecutioner class.

        Args:
            graph (MutliDiGraph): Graph representing the platform
            simulation (bool): Whether or not this is a simulation
            crash_dump (str): Path to crash dump JSON file.
        """

        # Graph object
        self.graph = graph

        # Simulation
        self.simulation = simulation

        # Inc ase it crashes horribly
        self.crash_dump = crash_dump
        self.crash_dump_keys = ["current_volume"]

        # Main logger
        self.logger = logging.getLogger('chempiler')

        # Smallest volume on the platform
        self.max_volume = self.get_max_syringe_volume()

    ##############
    # Crash Dump #
    ##############

    def _dump_graph(self):
        """
        Gets the useful info of the graph nodes into a dict and dumps them to
        file.
        """
        dump = {}
        for node in self.graph.nodes:
            node_crash_dump = {}
            class_node = self.graph[node]["class"]
            if (class_node == "ChemputerPump"
                    or class_node == "ChemputerValve"):
                continue
            for key, value in self.graph[node].items():
                if key in self.crash_dump_keys:  # if we want to save the item
                    node_crash_dump[key] = value

            dump[node] = node_crash_dump
        self._crash_dump_json(dump)

    def _crash_dump_json(self, data: Dict):
        """
        Dumps the dictionary to file
        """
        if self.crash_dump:
            with open(self.crash_dump, "w") as f_d:
                json.dump(data, f_d, indent=2)

    ##############
    # Separation #
    ##############

    @staticmethod
    def default_discriminant(
        positive_edge=False,
        negative_edge=False,
        sensitivity=5,
        min_points=6
    ) -> Callable[[Sequence[float]], bool]:
        """
        Factory method to return a customized discriminant function with the
        given properties.

        Args:
            positive_edge (bool, optional): Detect phase change when
                conductivity measurement goes up.
            negative_edge (bool, optional): Detect phase change when
                conductivity measurment goes down.
            sensitivity (int, optional): How many standard deviations away from
                the window mean should a conductivity reading be to be
                interpreted as a phase change.
            min_points (int, optional): Minimum number of conductivit
                measurement before a phase change can occur. The same paramter
                dictates the window size for the moving average:
                `window_size = min_points - 1`.

        Returns:
            Callable: A (disciminant) function that takes a series of
                measurement and decides whether a phase change has occurred.
        """

        def discriminant(points: Sequence[float]) -> bool:
            """
            This closes over the parameters passed to `default_discriminant`
            and is never accessed directly.

            Args:
                points: All conductivity measurements performed so far, with
                    `points[0]` being the first measurement and `points[-1]`
                    the current one.

            Returns:
                bool: Whether phase change has occurred (True) or not (False).
            """
            # collect at least 6 points before making a judgement
            if len(points) < min_points:
                return False
            # maximum standard deviation in the absence of a phase change
            std = max(statistics.pstdev(points[-min_points:-1]), 5.0)
            delta = points[-1] - statistics.mean(points[-min_points:-1])
            if ((delta > sensitivity * std and positive_edge)
                    or (-delta > sensitivity * std and negative_edge)):
                return True
            return False
        return discriminant

    def attached_conductivity_sensor(self, node_name: str):
        """
        Iterates over the predecessors of `node_name` and returns the first
        device that looks like a conductivity sensor (has `conductivity`
        attribute).

        Args:
            node_name (str): Name of a node in the graph

        Returns:
            Device object representing the conductivity sensor attached to the
            node.

        Raises:
            KeyError: An error if conductivity sensor is not found.
        """
        for node in self.graph.predecessors(node_name):
            node_object = self.graph.obj(node)
            if node_object.__class__.__name__ == 'ConductivitySensor':
                return node_object
        raise KeyError(
            "ERROR: node {0} has no conductivity sensor attached!".format(
                node_name))

    def separate_phases(
        self,
        separator_flask: str,
        lower_phase_target: str,
        upper_phase_target: str,
        dead_volume_target: str = None,
        step_size_milliliters: float = 1,
        discriminant: Callable[[Sequence[float]], bool] = None,
        lower_phase_port: str = None,
        upper_phase_port: str = None,
        dead_volume_port: str = None,
        lower_phase_through: str = None,
        upper_phase_through: str = None,
        dead_volume_through: str = None,
    ) -> None:
        """
        Routine for separating layers in the automated sep funnel based on the
        conductivity sensor. Draws a known amount into the tube, measures
        response, then keeps removing portions and recording the conductivity
        reading until calling `discriminant` with all recorded conductivity
        values results in a return a `True`thy value. When not specified,
        `discriminant` is set to `default_discriminant` sensitive to both
        positive and negative changes in conductivity.

        Hessam wrote this and it works so no need for a rewrite

        Args:
            separator_flask (str): name of the graph node corresponding to
                                   separator flask
            lower_phase_target (str): name of the flask the lower phase will be
                                      deposited to
            upper_phase_target (str): name of the flask the upper phase will be
                                      deposited to
            dead_volume_target (str or None): name of the flask the dead volume
                will be deposited to; if not set dead volume is not removed
            step_size_milliliters (float): volume of the individual withdrawals
                                           in mL
            discriminant (function): callback which gets passed all conductivity
                values up to current point and returns True or False indicating
                whether or not a phase change has been detected
            lower_phase_port (str): Optional. Port on lower_phase_target to use.
            upper_phase_port (str): Optional. Port on upper_phase_target to use.
            dead_volume_port (str): Optional. Port on dead_volume_target to use.
            lower_phase_through (str): Optional. Node to go through on way to
                lower_phase_target.
            upper_phase_through (str): Optional. Node to go through on way to
                upper_phase_target.
            dead_volume_through (str): Optional. Node to go through on way to
                dead_volume_target.
        """

        # default to `default_discriminant` with positive and negative edge
        # detection
        if not discriminant:
            discriminant = self.default_discriminant(True, True)
        # acquire sensor
        sensor_device = self.attached_conductivity_sensor(separator_flask)

        self.logger.info("Starting separation")

        # prime sensor
        self.move(
            src=separator_flask,
            dest=lower_phase_target,
            volume=constants.SEPARATION_DEFAULT_PRIMING_VOLUME,
            initial_pump_speed=constants.SEPARATION_DEFAULT_INITIAL_PUMP_SPEED,
            mid_pump_speed=constants.SEPARATION_DEFAULT_MID_PUMP_SPEED,
            end_pump_speed=constants.SEPARATION_DEFAULT_END_PUMP_SPEED,
            dest_port=lower_phase_port,
            through_nodes=lower_phase_through
        )

        readings = []
        # make an initial reading
        if not self.simulation:
            readings.append(sensor_device.conductivity)
            self.logger.info(
                "Initial sensor reading is {0:.2f}.".format(readings[0]))

        # start separation by repeatedly withdrawing some of the lower phase
        # until the ratio between current and initial readings is outside the
        # range `threshold`, `1/threshold`
        separator_pump = None
        for neighbor in self.graph.graph.neighbors(separator_flask):
            if self.graph.node_can_route(neighbor):
                for valve_neighbor in self.graph.graph.neighbors(neighbor):
                    if self.graph.node_can_pump(valve_neighbor):
                        separator_pump = valve_neighbor
        if not separator_pump:
            raise ChempilerError(f'No pump found attached to {separator_flask}')

        initial_pump_speed = constants.SEPARATION_DEFAULT_INITIAL_PUMP_SPEED

        while True:
            if (not (self.graph[separator_pump]['current_volume']
                     + step_size_milliliters
                     < self.graph[separator_pump]['max_volume'])):
                self.move(
                    src=separator_pump,
                    dest=lower_phase_target,
                    dest_port=lower_phase_port,
                    volume=self.graph[separator_pump]['current_volume'],
                    initial_pump_speed=initial_pump_speed,
                    mid_pump_speed=constants.SEPARATION_DEFAULT_MID_PUMP_SPEED,
                    end_pump_speed=constants.SEPARATION_DEFAULT_END_PUMP_SPEED,
                    through_nodes=lower_phase_through
                )
            self.move(
                src=separator_flask,
                dest=separator_pump,
                volume=step_size_milliliters,
                initial_pump_speed=initial_pump_speed,
                mid_pump_speed=constants.SEPARATION_DEFAULT_MID_PUMP_SPEED,
                end_pump_speed=constants.SEPARATION_DEFAULT_END_PUMP_SPEED,
            )

            if self.simulation:
                self.logger.info("This is where the magic happens")
                break
            else:
                readings.append(sensor_device.conductivity)
                self.logger.info("Sensor reading is {0}.".format(readings[-1]))
                if not discriminant(readings):
                    self.logger.info("Nope still the same phase.")
                else:
                    self.logger.info("Phase changed! Hurrah!")
                    break

        if self.graph[separator_pump]['current_volume']:
            self.move(
                src=separator_pump,
                dest=lower_phase_target,
                dest_port=lower_phase_port,
                volume=self.graph[separator_pump]['current_volume'],
                initial_pump_speed=initial_pump_speed,
                mid_pump_speed=constants.SEPARATION_DEFAULT_MID_PUMP_SPEED,
                end_pump_speed=constants.SEPARATION_DEFAULT_END_PUMP_SPEED,
                through_nodes=lower_phase_through
            )
        if dead_volume_target and dead_volume_target != separator_flask:
            # If dead volume in graph use it
            dead_volume = constants.SEPARATION_DEAD_VOLUME
            if 'dead_volume' in self.graph[separator_flask]:
                dead_volume = self.graph[separator_flask]['dead_volume']

            # withdraw separator dead volume
            self.logger.info("Now withdrawing dead volume...")
            self.move(
                src=separator_flask,
                dest=dead_volume_target,
                volume=dead_volume,
                initial_pump_speed=initial_pump_speed,
                mid_pump_speed=constants.SEPARATION_DEFAULT_MID_PUMP_SPEED,
                end_pump_speed=constants.SEPARATION_DEFAULT_END_PUMP_SPEED,
                dest_port=dead_volume_port,
                through_nodes=dead_volume_through
            )

        if upper_phase_target == separator_flask:  # i.e. keep the stuff
            self.logger.info("Done.")

        else:
            # transfer the upper layer to its destination
            self.logger.info("Done. Now transferring the upper layer...")
            volume = self.graph[separator_flask]["max_volume"]
            self.move(
                src=separator_flask,
                dest=upper_phase_target,
                volume=volume,
                initial_pump_speed=initial_pump_speed,
                mid_pump_speed=constants.SEPARATION_DEFAULT_MID_PUMP_SPEED,
                end_pump_speed=constants.SEPARATION_DEFAULT_END_PUMP_SPEED,
                dest_port=upper_phase_port,
                through_nodes=upper_phase_through
            )
            self.logger.info("Done.")

    ###########
    # Connect #
    ###########

    def connect_valve(self, valve: str, src_port: int, dest_port: int):
        """Turns the valve to a port

        Arguments:
            valve {str} -- Name of the valve
            port {int} -- Port to turn to
        """
        if (("route", src_port, dest_port)
                in self.graph[valve]["obj"].capabilities):
            valve_obj = self.graph.obj(valve)
            valve_obj.execute(**{"cmd": ("route", src_port, dest_port)})
            self.logger.info(
                f"Switched valve {valve} routing {src_port} to {dest_port}")

        else:
            raise ValueError(
                f'("route", {src_port}, {dest_port}) is an invalid command for\
 {valve}')

    def connect_nodes(
        self,
        src: str,
        dest: str,
        src_port: Union[str, int] = "",
        dest_port: Union[str, int] = "",
    ) -> None:
        """Connects two nodes together by switching necessary valves.

        Args:
            src (str): Source valve
            dest (str): Destination Valve
            src_port (int): Source Port
            dest_port (int): Destination Port
        """
        src_port, dest_port = self.assign_default_ports(
            src, dest, src_port, dest_port, connect=True)

        # Backbone can't be used for connections as pumps is attached to
        # valve -1 port
        path = self.graph.find_path(
            src=src,
            dest=dest,
            src_port=src_port,
            dest_port=dest_port,
            use_backbone=False,
            connect=True,
        )

        # Acquire device locks
        devices_to_lock = [
            step.src
            for step in path
            if self.graph.node_is_valve(step.src)
        ]
        for device in devices_to_lock:
            self.graph.acquire(device)

        # Operations returned for testing purposes
        operations = []
        prev_step = None
        for step in path:
            if self.graph.node_is_valve(step.src):
                operations.append(
                    (step.src, ('route', prev_step.dest_port, step.src_port)))
                self.connect_valve(step.src, prev_step.dest_port, step.src_port)

            prev_step = step

        # Release device locks
        for device in devices_to_lock:
            self.graph.release(device)

        return operations

    #########
    # Utils #
    #########

    def get_pump_from_valve_name(self, valve_name: str):
        """Gets the attached pump name and object from a ChemputerValve

        Arguments:
            valve_name {str} -- Name of the valve

        Returns:
            ChemputerPump -- ChemputerPump object
        """

        # Should only ever return 1 pump, else the topology is broken
        pump = [
            n for n in self.graph.neighbors(valve_name)
            if self.graph.node_can_pump(n)
        ]

        if pump:
            # Return first pump object
            return self.graph[pump[0]]["obj"]
        return None

    def get_max_syringe_volume(self) -> float:
        """Gets the smallest volume pump in the graph.
        This is the rate-limiting pump in the platform.

        Returns:
            float: Minimal volume of the platform
        """

        # Get all pumps in the graph
        pumps = [
            p for p in self.graph.nodes
            if self.graph.node_can_pump(p)
        ]
        if pumps:
            # Returns the smallest maximum volume of the pumps
            return min([self.graph[p]["max_volume"] for p in pumps])
        return None

    def routing_nodes(self, full_path: list) -> (list, list):
        """Finds all nodes and valves that aren't concerned with pumps
        These nodes just route liquid from one place to another

        Arguments:
            full_path {list} -- Full path of steps to execute

        Returns:
            list, list -- Routing nodes and routing valves
        """

        route_nodes, route_valves = [], []

        for step in full_path:

            if self.graph.node_is_valve(step.src):
                if not self.get_pump_from_valve_name(step.src):
                    # Src valve with no pump attached
                    route_valves.append(step.src)

                    # Still a routing node so add to list
                    route_nodes.append(step.src)
            else:
                # Src node that isn't a valve
                route_nodes.append(step.src)

            if self.graph.node_is_valve(step.dest):
                if not self.get_pump_from_valve_name(step.dest):
                    # Dest valve with no pump attached
                    route_valves.append(step.dest)

                    # Still a route node so add to list
                    route_nodes.append(step.dest)
            else:
                # Dest node that isn't a valve
                route_nodes.append(step.dest)

        # Return unique lists of each
        return list(set(route_nodes)), list(set(route_valves))

    def connect_routing_valve_cmds(self, valves: list, full_path: list):
        """Connects all valves that just route liquid

        Arguments:
            valves {list} -- Valves to connect
            full_path {list} -- Full list of steps
        """
        prev_step = None
        cmds = []
        for step in full_path:
            # Either source or dest can be not connected to -1
            if step.src in valves and prev_step:

                cmds.append((self.graph.obj(step.src), self.connect_valve_cmd(
                    step.src, prev_step.dest_port, step.src_port)))

            prev_step = step
        return cmds

    def prune_steps(self, path: list, routing_nodes: list) -> list:
        """Prunes all the stpes in the movement path, removing pure routes
        and combining routes together

        Arguments:
            path {list} -- Movement path through the graph
            routing_nodes {list} -- Nodes that are considered routing

        Returns:
            list -- Path with steps pruned
        """

        # Remove full routing steps
        path = self.remove_full_routing_steps(path, routing_nodes)

        # Combine steps containing routes
        path = self.combine_steps_with_routes(path, routing_nodes)

        return path

    def remove_full_routing_steps(
            self, path: list, routing_nodes: list) -> list:
        """Removes steps from the path that are purely routing
        E.g [cartridge1, cartridge2], [cartridge2, cartridge3] etc.

        Arguments:
            path {list} -- Movement path through the graph
            routing_nodes {list} -- List of nodes that are considered `routing`

        Returns:
            list -- Path with this kind of routing steps removed
        """
        # Remove all steps where the src and dest are routing
        for i in reversed(range(len(path))):
            step = path[i]
            if step.src in routing_nodes and step.dest in routing_nodes:
                path.pop(i)
        return path

    def combine_steps_with_routes(
        self,
        path: List[List[Union[str, str, Tuple]]],
        routing_nodes: List[str]
    ) -> List[List[Union[str, str, Tuple]]]:
        """Combines steps that contain a pump and route together
        E.g. [valve1, cartridge1], [cartridge1, valve2] would become
             [valve1, valve2]

        Args:
            path (List[List[Union[str, str, Tuple]]]): List of steps to combine
            routing_nodes (List[str]): List of nodes that act as routing nodes

        Returns:
            List[List[Union[str, str, Tuple]]]: List of combined steps
        """

        # List to hold the combined steps
        replacements = []

        # Iterate through all steps in the movement path
        for pos, step in enumerate(path):
            # Break out if the next element is out of bounds
            if pos + 1 == len(path):
                break
            next_step = path[pos + 1]

            # Current step dest and next step src are routing nodes
            if step.dest in routing_nodes and next_step.src in routing_nodes:
                # Build replacement, logging the position in the list
                replacements.append((
                    pos,
                    ChempilerPathStep(
                        step.src,
                        next_step.dest,
                        step.src_port,
                        next_step.dest_port
                    )
                ))

        # Remove both steps and replace with combined step
        for iteration, rep in enumerate(replacements):
            pos, item = rep[0] - iteration, rep[1]
            path.pop(pos)
            path.pop(pos)
            path.insert(pos, item)

        return path

    def assign_default_ports(
            self, src, dest, src_port, dest_port, connect=False):
        """If no port is given assign default port for that node class."""
        src_class = self.graph[src]['class']
        dest_class = self.graph[dest]['class']
        if connect:
            DEFAULT_PORTS = constants.DEFAULT_CONNECT_PORTS
        else:
            DEFAULT_PORTS = constants.DEFAULT_PORTS

        if src_port in [None, '']:
            if src_class in DEFAULT_PORTS:
                src_port = DEFAULT_PORTS[src_class]['src']
        else:
            try:
                src_port = int(src_port)
            except ValueError:
                pass

        if dest_port in [None, '']:
            if dest_class in DEFAULT_PORTS:
                dest_port = DEFAULT_PORTS[dest_class]['dest']
        else:
            try:
                dest_port = int(dest_port)
            except ValueError:
                pass

        return src_port, dest_port

    def split_movement_path(self, movement_path):
        """If movement path contains loop, split path into multiple paths at
        appropriate points so that every path only goes over any node once.
        """
        split_path = [[]]
        passed_nodes = []
        for step in movement_path:
            if step.src in passed_nodes:
                final_node = split_path[-1][-1].dest
                if self.graph.node_can_route(final_node):
                    final_node_pump = self.get_pump_from_valve_name(
                        final_node).name
                    split_path[-1].append(
                        ChempilerPathStep(
                            final_node,
                            final_node_pump,
                            src_port=-1,
                            dest_port=0
                        )
                    )

                    split_path.append([ChempilerPathStep(
                        final_node_pump,
                        step.src,
                        src_port=0,
                        dest_port=-1,
                    )])
                else:
                    split_path.append([])
                passed_nodes = []
            split_path[-1].append(step)
            passed_nodes.append(step.src)
        return split_path

    ##############
    # Pipelining #
    ##############

    def get_pipelined_steps(
        self,
        src: str,
        dest: str,
        volume: float,
        src_port: str = "",
        dest_port: str = "",
        speed=None,
        initial_pump_speed: float = constants.DEFAULT_INITIAL_PUMP_SPEED,
        mid_pump_speed: float = constants.DEFAULT_MID_PUMP_SPEED,
        end_pump_speed: float = constants.DEFAULT_END_PUMP_SPEED,
        through_nodes: Union[str, List] = "",
        use_backbone: bool = True,
        repeats: int = 1,
    ):
        """Given move method args, get pipelined steps."""
        if volume <= 0:
            self.logger.info(
                f'Trying to move volume <= 0 ({volume}). Not doing anything...')
            return []

        if speed:
            initial_pump_speed = speed
            mid_pump_speed = speed
            end_pump_speed = speed

        # Check for illegal args
        self.check_move_args(
            src=src,
            dest=dest,
            volume=volume,
            src_port=src_port,
            dest_port=dest_port,
            speed=speed,
            initial_pump_speed=initial_pump_speed,
            mid_pump_speed=mid_pump_speed,
            end_pump_speed=end_pump_speed,
            through_nodes=through_nodes,
            use_backbone=use_backbone,
        )

        # Assign default ports if no ports given.
        src_port, dest_port = self.assign_default_ports(
            src, dest, src_port, dest_port)

        pipelined_steps = []

        # Get path from src to dest
        movement_path = self.graph.find_path(
            src, dest, src_port, dest_port, through_nodes, use_backbone
        )

        # Alt path is a list of paths, but a normal path is just a single path
        # so put it in a list so that it can be used in for loop below.
        if type(movement_path[0]) != list:
            movement_path = [movement_path]

        if len(movement_path) == 1:
            movement_path = self.split_movement_path(movement_path[0])

        self.logger.debug(f'Movement path: {movement_path}')

        # Alternative paths
        if len(movement_path) > 1:
            vol_added = 0
            try:
                pump_max_volume = self.max_volume
            except KeyError:
                raise KeyError(
                    f'Node "{movement_path[0][-1].dest}" has no max volume\
 attribute.')

            while vol_added < volume:
                vol_to_add = min(pump_max_volume, volume - vol_added)
                new_pipelined_steps = []
                for item in movement_path:
                    new_pipelined_steps += self.pipeline_path(
                        item,
                        vol_to_add,
                        initial_pump_speed,
                        mid_pump_speed,
                        end_pump_speed
                    )

                # Get most efficient offset
                offset = 1
                # if added_first_vol:
                while len(pipelined_steps) - offset >= 0:
                    test_steps = self.copy_pipelined_steps(pipelined_steps)
                    test_steps = self.insert_steps(
                        test_steps, new_pipelined_steps, offset)
                    try:
                        self.validate_one_command_per_group_per_node(test_steps)
                    except ChempilerError:
                        break
                    offset += 1
                offset = max(offset - 1, 0)

                # Add pipelined steps at offset
                pipelined_steps = self.insert_steps(
                    pipelined_steps, new_pipelined_steps, offset)
                vol_added += vol_to_add

        else:
            pipelined_steps.extend(self.pipeline_path(
                movement_path[0],
                volume,
                initial_pump_speed,
                mid_pump_speed,
                end_pump_speed
            ))

        if repeats > 1:
            self.pipeline_repeated_steps(pipelined_steps, repeats)

        return pipelined_steps

    def pipeline_repeated_steps(self, pipelined_steps, repeats):
        """Given the final pipelined steps list of the move command, duplicate
        it `repeats` times, and pipeline the duplicates into the original
        pipelined steps list and return it.
        """
        # Make copies
        original_pipelined_steps = self.copy_pipelined_steps(pipelined_steps)
        new_pipelined_steps = self.copy_pipelined_steps(
            original_pipelined_steps
        )

        # Get most efficient offset
        offset = 1
        while len(pipelined_steps) - offset >= 0:
            test_steps = self.copy_pipelined_steps(pipelined_steps)
            test_steps = self.insert_steps(
                test_steps, new_pipelined_steps, offset)
            try:
                self.validate_one_command_per_group_per_node(test_steps)
            except ChempilerError:
                break
            offset += 1
        offset = max(offset - 1, 0)

        # Add duplicate steps at offset
        for _ in range(repeats - 1):
            pipelined_steps = self.insert_steps(
                pipelined_steps,
                self.copy_pipelined_steps(original_pipelined_steps),
                offset
            )

        return pipelined_steps

    def insert_steps(self, pipelined_steps, steps_to_add, offset):
        """Insert steps_to_add pipelined step list into pipelined_steps
        pipelined steps list at offset.

        Offset should be positive integer that indicates how far back in
        pipelined_steps to insert.
        """
        pipelined_steps_len = len(pipelined_steps)
        if not pipelined_steps:
            pipelined_steps = steps_to_add
        else:
            for j, item in enumerate(steps_to_add):
                pos = pipelined_steps_len - offset + j
                if pos >= len(pipelined_steps):
                    pipelined_steps.append(item)
                else:
                    pipelined_steps[pos].extend(item)
        return pipelined_steps

    def pipeline_path(
        self,
        path,
        volume,
        initial_pump_speed,
        mid_pump_speed,
        end_pump_speed,
    ):
        path = copy.deepcopy(path)
        path_src, path_dest = path[0].src, path[-1].dest
        # Get all nodes that are classed as a route
        route_nodes, route_valves = self.routing_nodes(path)

        # Connect all valves that act as routes
        connect_routing_valve_cmds = self.connect_routing_valve_cmds(
            route_valves, path)

        # If moving to a pump, remove the last step as it is causes the valve to
        # try and route from -1 to -1 and the pump to dispense the liquid that
        # has already been moved to it.
        if self.graph.node_can_pump(path[-1].dest):
            path.pop()

        if self.graph.node_can_pump(path[0].src):
            path.pop(0)

        # No path, just return or raise Exception
        if not path:
            self.logger.info(
                f"No valid path found for {path_src} -- {path_dest}")
            return

        path_s = f'Using path: {path[0].src} -> {path[0].dest}'
        if len(path) > 1:
            for item in path[1:]:
                path_s += f' -> {item.src}'
            path_s += f' -> {path[-1].dest}'
        self.logger.debug(path_s)

        # Clean up the steps, ensuring only pump steps remain
        path = self.prune_steps(path, route_nodes)

        pipelined_step_list = self.pipeline_step_list(
            path_src,
            path_dest,
            path,
            volume,
            initial_pump_speed,
            mid_pump_speed,
            end_pump_speed
        )

        pipelined_step_list[0].extend(connect_routing_valve_cmds)

        return pipelined_step_list

    def get_step_list_min_pump_volume(self, step_list: List[Tuple]) -> float:
        """Get the minimum pump volume of all pumps associated with the given
        step list.

        Args:
            step_list (List[Tuple]): Step list to look for associated pump
                volumes.

        Returns:
            float: Minimum pump volume of all pumps associated with step_list.
        """
        min_volume = 10000
        for step in step_list:
            src = step.src
            dest = step.dest
            src_node = self.graph[src]
            dest_node = self.graph[dest]
            src_class = src_node['class']
            dest_class = dest_node['class']

            # Src is pump, update min volume
            if src_class == constants.CHEMPUTER_PUMP:
                min_volume = min(min_volume, src_node['max_volume'])

            # Dest is pump, update min volume
            if dest_class == constants.CHEMPUTER_PUMP:
                min_volume = min(min_volume, dest_node['max_volume'])

            # Src is valve, look for pump to update min volume
            if src_class == constants.CHEMPUTER_VALVE:
                src_pump = self.graph.get_pump_from_valve_name(src)
                if src_pump:
                    min_volume = min(
                        min_volume, self.graph[src_pump.name]['max_volume'])

            # Dest is valve, look for pump to update min volume
            if dest_class == constants.CHEMPUTER_VALVE:
                dest_pump = self.graph.get_pump_from_valve_name(dest)
                if dest_pump:
                    min_volume = min(
                        min_volume, self.graph[dest_pump.name]['max_volume'])

        return min_volume

    def pipeline_step_list(
        self,
        src,
        dest,
        step_list,
        volume,
        initial_pump_speed,
        mid_pump_speed,
        end_pump_speed
    ):
        pipelined_step_list = []
        pipeline_pos = 0

        # Flag to know if recursive call has been made during path.
        recursive = False

        original_volume = volume
        # Keep going as long as the volume is above 0
        # while volume > 0:
        # Minimal volume if volume is greater than that, else the current
        # volume value
        max_volume = self.get_step_list_min_pump_volume(step_list)
        vol = max_volume if volume > max_volume else volume

        # Subtract vol for first movement
        volume -= vol
        # Execute each step
        for pos, step in enumerate(step_list):
            if pipeline_pos >= len(pipelined_step_list):
                pipelined_step_list.append([])
            # Get speed to use for pumping
            speed = mid_pump_speed

            if pos == 0:
                # First step, src pump
                if self.graph[src]['class'] == 'ChemputerPump':
                    speed = mid_pump_speed
                # First step, src not pump
                else:
                    speed = initial_pump_speed

            # Last step
            if pos == len(step_list) - 1:
                speed = end_pump_speed

                # Last step, moving to pump
                if self.graph[dest]['class'] == 'ChemputerPump':
                    speed = initial_pump_speed

            # Start pumping again if the first 2 steps are cleared
            # and only if the volume is greater than the max volume
            if pos > 0 and pos == 2 and volume > 0:
                # Subtract vol for every overlapped movement
                next_step_list = self.pipeline_step_list(
                    src,
                    dest,
                    step_list,
                    volume,
                    initial_pump_speed,
                    mid_pump_speed,
                    end_pump_speed
                )
                recursive = True
                for i in range(len(next_step_list)):
                    actual_i = pipeline_pos + i
                    while actual_i >= len(pipelined_step_list):
                        pipelined_step_list.append([])
                    pipelined_step_list[actual_i].extend(next_step_list[i])

            step.speed = speed
            step.volume = vol

            devices, cmds = self.execute_step(step, vol, speed)
            for device_group, cmd_group in zip(devices, cmds):
                if pipeline_pos >= len(pipelined_step_list):
                    pipelined_step_list.append([])
                for device, cmd in zip(device_group, cmd_group):
                    pipelined_step_list[pipeline_pos].append((device, cmd))
                pipeline_pos += 1

        # If movement path is too short to be staggered, do recursive call here
        # after end of path.
        if not recursive and volume:
            # Subtract vol for every overlapped movement
            next_step_list = self.pipeline_step_list(
                src,
                dest,
                step_list,
                volume,
                initial_pump_speed,
                mid_pump_speed,
                end_pump_speed
            )
            for i in range(len(next_step_list)):
                actual_i = pipeline_pos + i
                while actual_i >= len(pipelined_step_list):
                    pipelined_step_list.append([])
                pipelined_step_list[actual_i].extend(next_step_list[i])

        self.validate_pipelined_step_list(
            step_list,
            pipelined_step_list,
            original_volume,
            self.get_step_list_min_pump_volume(step_list),
            src,
            dest,
        )
        return pipelined_step_list

    def copy_pipelined_steps(self, pipelined_steps):
        """Deep copies step details but shallow copies device objects. This is
        necessary as copy.deepcopy throws error in Python 3.6.
        """
        new_pipelined_steps = []
        for step_group in pipelined_steps:
            new_pipelined_steps.append([])
            for device, cmd in step_group:
                new_pipelined_steps[-1].append((device, copy.deepcopy(cmd)))
        return new_pipelined_steps

    def print_pipelined_step_list(self, pipelined_step_list):
        self.logger.debug('[')
        indent = '    '
        for step_group in pipelined_step_list:
            self.logger.debug(indent + '[')
            for device, cmd in step_group:
                self.logger.debug(f'{indent*2}("{device.name}", {cmd}),')
            self.logger.debug(indent + '],')
        self.logger.debug(']')

    ########
    # Move #
    ########

    def move(
        self,
        src: str,
        dest: str,
        volume: float,
        src_port: str = "",
        dest_port: str = "",
        speed=None,
        initial_pump_speed: float = constants.DEFAULT_INITIAL_PUMP_SPEED,
        mid_pump_speed: float = constants.DEFAULT_MID_PUMP_SPEED,
        end_pump_speed: float = constants.DEFAULT_END_PUMP_SPEED,
        through_nodes: Union[str, List] = "",
        use_backbone: bool = True,
        repeats: int = 1,
    ):
        """Moves liquid from one node to another

        Arguments:
            src (str): Source node
            dest (str): Destination node
            volume (float): Volume to move
            initial_pump_speed (float): Speed to pull in liquid @ start
            mid_pump_speed (float): Speed to move liquid in the middle
            end_pump_speed (float): Speed to dispense liquid @ end

        Keyword Arguments:
            through_nodes (Optional[str, List]): Nodes to pass through
            src_port (str): Source port to use, if available
            dest_port (str): Destination port to use, if available
            use_backbone (bool): Find a path using the backbone of the\
                Chemputer (default: {True})
            repeats (int): How many times the move command should be executed.
                This is useful in the case, for example, that you want to move
                3x3 mL somewhere, but you want to do it efficiently using
                pipelined steps. Three separate move commands would be less
                efficient than using repeats=3 as repeats=3 means everything
                is pipelined.
        """
        volume_to_move = volume
        volume_to_move_for_tracking = volume
        if volume == 'all':
            current_volume = self.graph[src]['current_volume']
            # Add current volume to little extra just to make sure transfer
            # is complete.
            volume_to_move = current_volume + max(
                constants.MOVE_ALL_MIN_EXCESS,
                current_volume * constants.MOVE_ALL_EXCESS_FACTOR
            )

            # Don't include excess when updating current_volumes in the graph.
            volume_to_move_for_tracking = current_volume

        # Get pipelined steps
        pipelined_steps = self.get_pipelined_steps(
            src=src,
            dest=dest,
            volume=volume_to_move,
            src_port=src_port,
            dest_port=dest_port,
            speed=speed,
            initial_pump_speed=initial_pump_speed,
            mid_pump_speed=mid_pump_speed,
            end_pump_speed=end_pump_speed,
            through_nodes=through_nodes,
            use_backbone=use_backbone,
            repeats=repeats
        )

        if not pipelined_steps:
            return

        # Logging
        self.print_pipelined_step_list(pipelined_steps)

        self.logger.info(self.move_log_message(
            volume=volume_to_move, src=src, dest=dest, src_port=src_port,
            dest_port=dest_port, initial_pump_speed=initial_pump_speed,
            mid_pump_speed=mid_pump_speed, end_pump_speed=end_pump_speed,
            through_nodes=through_nodes, use_backbone=use_backbone
        ))

        # Execute piplined steps
        self.execute_pipelined_steps(pipelined_steps)

        self.update_volume_tracking(
            volume_to_move_for_tracking, src, dest, src_port, dest_port)

        self._dump_graph()

        return pipelined_steps

    def update_volume_tracking(
        self,
        volume,
        src,
        dest,
        src_port,
        dest_port
    ):
        src_node = self.graph[src]

        # Don't update volume tracking when moving inert gas
        if self.node_is_inert_gas(src):
            return

        # Don't update volume tracking when moving inert gas in a split
        # src -> pump + pump -> dest double move command. This works because
        # the first move will not update the pump current volume as inert gas
        # is being moved. So can check for that here, and make sure no update
        # is made when the gas is moved from the pump to the dest.
        elif src_node['class'] == constants.CHEMPUTER_PUMP:
            if src_node['current_volume'] == 0:
                return

        # Update src volume, ignoring collection flask of rotavap
        if src_port != 'collect':
            # Don't track volumes in rotary evporator collection flask
            src_node['current_volume'] -= volume
            if src_node['current_volume'] < 0:
                self.logger.warning(
                    f'Negative flask volume: {src}\
{src_node["current_volume"]} mL. Setting to 0.')
                src_node['current_volume'] = 0

        # Update dest volume, ignoring collection flask of rotavap
        if dest_port != 'collect':
            dest_node = self.graph[dest]
            dest_node['current_volume'] +=\
                volume
            current_volume = dest_node['current_volume']

            # Check if 'max_volume' given in graph. For modular wheel it is
            # not given.
            if 'max_volume' in dest_node:
                max_volume = dest_node['max_volume']
                if current_volume > max_volume:
                    self.logger.warning(
                        f'Overfilled flask volume: {dest}\
    {current_volume} mL exceeds {dest} max volume {max_volume} mL. Setting\
    current_volume to {max_volume} mL.')
                    dest_node['current_volume'] = max_volume

    def node_is_inert_gas(self, node: str) -> bool:
        """Return ``True`` if node is inert gas flask otherwise return
        ``False``.
        """
        node_data = self.graph.nodes[node]
        if node_data['class'] == constants.CHEMPUTER_FLASK:
            if 'chemical' in node_data:
                if node_data['chemical'].lower() in constants.INERT_GAS_NAMES:
                    return True
        return False

    def move_duration(
        self,
        src: str,
        dest: str,
        volume: float,
        src_port: str = "",
        dest_port: str = "",
        speed=None,
        initial_pump_speed: float = constants.DEFAULT_INITIAL_PUMP_SPEED,
        mid_pump_speed: float = constants.DEFAULT_MID_PUMP_SPEED,
        end_pump_speed: float = constants.DEFAULT_END_PUMP_SPEED,
        through_nodes: Union[str, List] = "",
        use_backbone: bool = True,
        repeats: int = 1,
    ):
        """Get duration in seconds of move command corresponding to given
        paramters.
        """
        pipelined_steps = self.get_pipelined_steps(
            src=src,
            dest=dest,
            volume=volume,
            src_port=src_port,
            dest_port=dest_port,
            speed=speed,
            initial_pump_speed=initial_pump_speed,
            mid_pump_speed=mid_pump_speed,
            end_pump_speed=end_pump_speed,
            through_nodes=through_nodes,
            use_backbone=use_backbone,
            repeats=repeats
        )

        total_duration = 0
        path_duration = 0
        for step_group in pipelined_steps:
            group_duration = 0
            for _, cmd in step_group:
                cmd_duration = self.cmd_duration(cmd)
                if cmd_duration > group_duration:
                    group_duration = cmd_duration
            path_duration += group_duration

        total_duration += path_duration

        return total_duration

    def cmd_duration(self, cmd: Dict[str, Any]):
        """Get estimated duration of given cmd.

        Args:
            cmd (Dict[str, Any]): Command to get estimated duration from.
        """
        if 'volume' in cmd and 'speed' in cmd:
            return (cmd['volume'] / cmd['speed']) * 60
        return 1

    def move_locks(
        self,
        src: str,
        dest: str,
        volume: float,
        src_port: str = "",
        dest_port: str = "",
        speed=None,
        initial_pump_speed: float = constants.DEFAULT_INITIAL_PUMP_SPEED,
        mid_pump_speed: float = constants.DEFAULT_MID_PUMP_SPEED,
        end_pump_speed: float = constants.DEFAULT_END_PUMP_SPEED,
        through_nodes: Union[str, List] = "",
        use_backbone: bool = True,
        repeats: int = 1,
    ):
        """Get locks associated with move command corresponding to the given
        params.
        """
        # Use arbitrary volume if 'all' keyword used. Volume doesn't matter
        # here.
        if volume == 'all':
            volume = 10

        pipelined_steps = self.get_pipelined_steps(
            src=src,
            dest=dest,
            volume=volume,
            src_port=src_port,
            dest_port=dest_port,
            speed=speed,
            initial_pump_speed=initial_pump_speed,
            mid_pump_speed=mid_pump_speed,
            end_pump_speed=end_pump_speed,
            through_nodes=through_nodes,
            use_backbone=use_backbone,
            repeats=repeats
        )
        locks = []

        # Add all used valves/pumps to locks.
        for step_group in pipelined_steps:
            for device, _ in step_group:
                locks.append(device.name)
        src_node = self.graph[src]

        # Don't add reagent flasks to locks as they can be used by multiple
        # processes at once as long as different pumps/valves are being used to
        # withdraw the reagent.
        if (src_node['class'] == constants.CHEMPUTER_FLASK
                and src_node.get('chemical')):
            pass
        else:
            locks.append(src)

        locks = list(set(locks))
        ongoing_locks = [dest]
        unlocks = []
        return locks, ongoing_locks, unlocks

    def move_log_message(
        self,
        volume,
        src,
        dest,
        src_port,
        dest_port,
        initial_pump_speed,
        mid_pump_speed,
        end_pump_speed,
        through_nodes,
        use_backbone,
    ):
        msg = f'Moving {volume} mL from {src} ({src_port}) to {dest}\
 ({dest_port})'
        if through_nodes:
            if type(through_nodes) == str:
                through_nodes = [through_nodes]
            msg += f' through {", ".join(through_nodes)}'
        msg += f'. (Speed - Initial: {initial_pump_speed}, Mid:\
 {mid_pump_speed}, End: {end_pump_speed})'
        return msg

    ##############
    # Validation #
    ##############

    def check_move_args(
        self,
        src: str,
        dest: str,
        volume: float,
        src_port: str = "",
        dest_port: str = "",
        speed=None,
        initial_pump_speed: float = constants.DEFAULT_INITIAL_PUMP_SPEED,
        mid_pump_speed: float = constants.DEFAULT_MID_PUMP_SPEED,
        end_pump_speed: float = constants.DEFAULT_END_PUMP_SPEED,
        through_nodes: Union[str, List] = "",
        use_backbone: bool = True
    ):
        """Sanity check move command args."""

        self.validate_port(src, src_port)
        self.validate_port(dest, dest_port)

        # Check not trying to move greater than max volume.
        if self.graph.node_can_pump(src):
            pump_max_volume = self.graph[src]['max_volume']
            if volume > pump_max_volume:
                raise ChempilerError(
                    f"Trying to pump {volume} from pump with max volume\
 {pump_max_volume}")

        # Check dest has max volume and it is not less than move volume
        if self.graph.node_can_pump(dest):
            dest_max_volume = self.graph[dest]['max_volume']
            if volume > dest_max_volume:
                raise ChempilerError(f"Trying to pump {volume} to pump with\
 max volume {dest_max_volume}")

        # Check speeds are all legal
        for speed in [initial_pump_speed, mid_pump_speed, end_pump_speed]:
            if speed <= 0:
                raise ChempilerError("Move speeds must be greater than 0.")

            elif speed > 200:
                raise ChempilerError(
                    "Move speed too high. Max speed 200 mL/min.")

        # Check src/dest are different
        if src == dest and not through_nodes:
            raise ChempilerError(f"Trying to move to/from same node ({src}).")

    def validate_port(self, node, port):
        if node and port not in [None, '']:
            node_class = self.graph[node]['class']
            valid_ports = constants.VALID_PORTS[node_class]
            if port not in valid_ports:
                raise ChempilerInvalidPortError(node, node_class, port)

    def validate_len_pipeline(
        self,
        step_list,
        pipelined_step_list,
        volume,
        pump_max_volume,
        src,
        dest
    ):

        # Change backbone to any valve with a pump attached
        n_pump_step_groups = 0
        target_valves = []
        for step in step_list[1:]:
            if step.src in self.graph.find_valves_with_pumps():
                target_valves.append(step.src)
        if step_list[0].src in self.graph.find_valves_with_pumps():
            target_valves.append(step_list[0].src)
        if step_list[-1].dest in self.graph.find_valves_with_pumps():
            target_valves.append(step_list[-1].dest)

        for step_group in pipelined_step_list:
            pump_step_group = False
            for step in step_group:
                if self.graph.node_can_pump(step[0].name):
                    pump_step_group = True
            if pump_step_group:
                n_pump_step_groups += 1

        n_pump_volumes = math.ceil(volume / pump_max_volume)

        try:
            expected_n_pump_step_groups = self.expected_n_pump_step_groups(
                target_valves, n_pump_volumes, src, dest
            )
            assert n_pump_step_groups == expected_n_pump_step_groups
        except AssertionError:
            self.print_pipelined_step_list(pipelined_step_list)
            raise ChempilerError(
                f'Potential Chempiler Bug: Suspicious pipelined step list\
 length found.\n\
 Found pump groups: {n_pump_step_groups}\n\
 Expected pump groups: {expected_n_pump_step_groups}\n\
 Likely is a pipelining error.'
            )

    def validate_src_dest_volumes(
        self, src, dest, pipelined_step_list, volume
    ):
        src_step, dest_step = (), ()
        src_volume, dest_volume = 0, 0
        src_is_pump = self.graph.node_can_pump(src)
        dest_is_pump = self.graph.node_can_pump(dest)
        if dest_is_pump:
            return
        for step_group in pipelined_step_list:
            for step in step_group:
                if not src_step:
                    if (src_is_pump
                            and step[1]['cmd'][0] == 'source'
                            and self.graph.node_can_pump(step[0].name)):
                        src_step = step
                    elif (self.graph.node_can_pump(step[0].name)
                          and step[1]['cmd'][0] == 'sink'):
                        src_step = step
                    if src_step:
                        src_volume += step[1]['volume']

                else:
                    if (step[0].name == src_step[0].name
                            and step[1]['cmd'][0] == src_step[1]['cmd'][0]):
                        src_volume += step[1]['volume']

                if not dest_step:
                    if (dest_is_pump
                            and step[1]['cmd'][0] == 'sink'
                            and self.graph.node_can_pump(step[0].name)):
                        dest_step = step
                    elif (self.graph.node_can_pump(step[0].name)
                          and step[1]['cmd'][0] == 'source'):
                        dest_step = step
                    if dest_step:
                        dest_volume += step[1]['volume']

                else:
                    if (step[0].name == dest_step[0].name
                            and step[1]['cmd'][0] == dest_step[1]['cmd'][0]):
                        dest_volume += step[1]['volume']

        self.logger.debug(f'Validating src volume {src_step} {src_volume}')
        self.logger.debug(f'Validating dest volume {dest_step} {dest_volume}')
        try:
            assert src_volume == dest_volume == volume
        except AssertionError:
            self.print_pipelined_step_list(pipelined_step_list)
            raise ChempilerError(
                f'Fatal error: Volume leaving src ({src}) != volume arriving at\
 dest ({dest}) != target volume')

    def validate_one_command_per_group_per_node(self, pipelined_step_list):
        """Validate that nodes are only given one command per step group."""
        for step_group in pipelined_step_list:
            nodes_used = [step[0].name for step in step_group]
            try:
                assert len(nodes_used) == len(set(nodes_used))
            except AssertionError:
                raise ChempilerError(
                    'Fatal error: Same node used multiple times in step group.')
                # self.print_pipelined_step_list(pipelined_step_list)
            try:
                valves_used = [
                    item
                    for item in nodes_used
                    if self.graph.node_can_route(item)
                ]
                for valve in valves_used:
                    valve_pump = self.get_pump_from_valve_name(valve)
                    if valve_pump:
                        assert self.get_pump_from_valve_name(
                            valve).name not in nodes_used
            except AssertionError:
                raise ChempilerError(
                    'Fatal error: Pump valves switched during pump step group.')

    def validate_pump_moves(self, pipelined_step_list, src, dest):
        """Validate that no pump moves put the pump volume above its max or below
        zero.
        """
        pump_volumes = {}
        for step_group in pipelined_step_list:
            for step in step_group:
                if (self.graph.node_can_pump(step[0].name)
                        and not step[0].name in [src, dest]):
                    pump = step[0].name
                    cmd = step[1]['cmd'][0]
                    volume = step[1]['volume']

                    if pump not in pump_volumes:
                        pump_volumes[pump] = 0

                    if cmd == 'sink':
                        pump_volumes[pump] += volume
                    elif cmd == 'source':
                        pump_volumes[pump] -= volume
                    else:
                        raise ChempilerError(
                            'Invalid command given to pump. Valid commands:\
 "sink", "source"')

                    try:
                        assert 0 <= pump_volumes[pump] <= self.graph[
                            pump]['max_volume']
                    except AssertionError as e:
                        # print(pump_volumes[pump], step)
                        # self.print_pipelined_step_list(pipelined_step_list)
                        raise e

    def validate_valve_switches(self, pipelined_step_list):
        """
        Validate all valve switches.
        TODO: For every pump pair, validate that the path between them is clear.
        """
        for step_group in pipelined_step_list:
            for step in step_group:
                if self.graph[step[0].name]['class'] == 'ChemputerValve':
                    assert (step[1]['cmd'][1]
                            in constants.VALID_PORTS['ChemputerValve'])
                    assert (step[1]['cmd'][1]
                            in constants.VALID_PORTS['ChemputerValve'])

    def validate_pipelined_step_list(
        self,
        step_list,
        pipelined_step_list,
        volume,
        pump_max_volume,
        src,
        dest,
    ):
        """Sanity check on pipelined step list.
        Implemented: Check length of pipeline is consistent with expected length
                     after pipelining.

        TODO:
        * Validate all valve switches -1 <-> (0...5)
        """
        # If src is a valve then the actual src is a pump
        if self.graph.nodes[src]['class'] == constants.CHEMPUTER_VALVE:
            src = self.graph.get_pump_from_valve_name(src).name

        # If dest is a valve then the actual dest is a pump
        if self.graph.nodes[dest]['class'] == constants.CHEMPUTER_VALVE:
            dest = self.graph.get_pump_from_valve_name(dest).name

        self.validate_len_pipeline(
            step_list, pipelined_step_list, volume, pump_max_volume, src, dest)
        self.validate_src_dest_volumes(
            src, dest, pipelined_step_list, volume)
        self.validate_one_command_per_group_per_node(pipelined_step_list)
        self.validate_pump_moves(pipelined_step_list, src, dest)
        self.validate_valve_switches(pipelined_step_list)

    def execute_pipelined_steps(
        self,
        pipelined_steps,
    ):
        # Acquire device locks
        devices_to_lock = set([
            device.name
            for step_group in pipelined_steps
            for device, _ in step_group
        ])
        for device in devices_to_lock:
            self.graph.acquire(device)

        # Execute pipelined steps
        for step_group in pipelined_steps:
            # Blank log to separate command groups in log.
            self.logger.debug('')
            devices = []

            # Sinks should be performed first, otherwise it can create excessive
            # pressure which can cause leaks.
            sinks = [
                (device, cmd)
                for device, cmd in step_group
                if cmd["cmd"][0] == "sink"
            ]
            sources = [
                (device, cmd)
                for device, cmd in step_group
                if cmd["cmd"][0] == "source"
            ]
            routes = [
                (device, cmd)
                for device, cmd in step_group
                if cmd["cmd"][0] == "route"
            ]

            for cmd_list in [routes, sinks, sources]:
                for device, cmd in cmd_list:
                    self.execute_cmd(device, cmd)
                    devices.append(device)

            # Wait until all commands have finished executing
            for device in devices:
                device.wait_until_ready()

            # Pause after aspiration to allow pressure to equalize.
            if not self.simulation and sinks:
                time.sleep(constants.AFTER_ASPIRATION_WAIT)

        # Release locks on all devices used
        for device in devices_to_lock:
            self.graph.release(device)

    def expected_n_pump_step_groups(
        self, backbone_valves, n_pump_volumes, src, dest
    ):
        expected_n_pump_step_groups = (
            (len(backbone_valves) + 1) + (2 * (n_pump_volumes - 1))
        )
        if self.graph.node_can_pump(src):
            expected_n_pump_step_groups -= 1
        if self.graph.node_can_pump(dest):
            expected_n_pump_step_groups -= 1
        return expected_n_pump_step_groups

    #############
    # Execution #
    #############

    def execute_cmd(self, device, cmd):
        """Execute command and log message at same time.

        Args:
            device (ChemputerEthernetDevice): ChemputerAPI device object to use
                for executing command.
            cmd (Dict[str, Any]): Command to execute.
        """
        if cmd["cmd"][0] == "sink":
            self.logger.debug(
                f"Pumping {cmd['volume']} mL (Speed: {cmd['speed']})\
 Pump::{device.name}")

        elif cmd["cmd"][0] == "source":
            self.logger.debug(
                f"Dispensing {cmd['volume']} mL (Speed: {cmd['speed']})\
 Pump::{device.name}")

        elif cmd["cmd"][0] == "route":
            self.logger.debug(
                f"Switched valve {device.name} routing {cmd['cmd'][1]} to\
 {cmd['cmd'][2]}")

        device.execute(**cmd)

    def execute_step(
        self,
        step: list,
        volume: float,
        speed: float
    ):
        """Executes a single step of liquid movement

        Arguments:
            step {list} -- Step to execute
            volume {float} -- Volume to dispense
            speed (float): Speed to draw liquid
        """

        # self.logger.info(f"Executing Step: {step}")

        # Src is not a valve, pull in from dest pump
        # (Start of full movement path)
        if not self.graph.node_is_valve(step.src):
            devices, cmds = self.single_pump_valve_combo(
                step.dest, "sink", step.dest_port, volume, speed
            )

        # Dest is not a valve, dispense from src pump
        # (End of full movement path)
        elif not self.graph.node_is_valve(step.dest):
            devices, cmds = self.single_pump_valve_combo(
                step.src, "source", step.src_port, volume, speed
            )

        # Src and Dest are the same, valve dispensing back into itself
        # (valve1 -> valve1)
        elif step.src == step.dest:
            devices, cmds = self.single_pump_valve_combo(
                step.src, "source", step.src_port, volume, speed
            )
            devices, cmds = self.single_pump_valve_combo(
                step.dest, "sink", step.dest_port, volume, speed
            )

        # Src and Dest are different valves, move both pumps @ same time
        else:
            if (self.get_pump_from_valve_name(step.src)
                    and self.get_pump_from_valve_name(step.dest)):
                devices, cmds = self.dual_pump_valve_combo(
                    step.src,
                    step.dest,
                    step.src_port,
                    step.dest_port,
                    volume,
                    speed
                )
            elif self.get_pump_from_valve_name(step.src):
                devices, cmds = self.single_pump_valve_combo(
                    step.src, "source", step.src_port, volume, speed
                )
            elif self.get_pump_from_valve_name(step.dest):
                devices, cmds = self.single_pump_valve_combo(
                    step.dest, "sink", step.dest_port, volume, speed
                )
            else:
                raise Exception("Error executing step.")

        return devices, cmds

    def connect_valve_cmd(self, valve, src_port, dest_port):
        if (("route", src_port, dest_port)
                in self.graph[valve]["obj"].capabilities):
            return {"cmd": ("route", src_port, dest_port)}

        else:
            raise ValueError(
                f'("route", {src_port}, {dest_port}) is an invalid command for\
 {valve}')

    def single_pump_valve_combo(
        self,
        valve_name: str,
        cmd_type: str,
        port: Union[int, str],
        volume: float,
        speed: float
    ) -> None:
        """Sets a single valve and a single pump movement

        Args:
            valve_name (str): Name of the valve node
            cmd_type (str): Sink or source (Draw in or dispense)
            port (Union[int, str]): Port of the node
            volume (float): Volume to move
            speed (float): Speed to move liquid
        """
        # Get pump and valve object
        valve_obj = self.graph.obj(valve_name)
        pump_obj = self.get_pump_from_valve_name(valve_name)

        cmds = [
            [self.connect_valve_cmd(valve_name, port, constants.PUMP_PORT)],
            [{"cmd": (cmd_type, 0), "volume": volume, "speed": speed}]
        ]
        devices = [
            [valve_obj],
            [pump_obj]
        ]
        return devices, cmds

    def dual_pump_valve_combo(
        self,
        src: str,
        dest: str,
        from_port: Union[int, str],
        to_port: Union[int, str],
        volume: float,
        mid_pump_speed: float
    ) -> None:
        """Sets two valves and moves two pumps simultaneously

        Args:
            src (str): Source node
            dest (str): Destination node
            from_port (Union[int, str]): Source node port
            to_port (Union[int, str]): Destination node port
            volume (float): Volume to move
            mid_pump_speed (float): Speed to move
        """
        # Get both pump and valve objects
        src_valve, dest_valve = self.graph.obj(src), self.graph.obj(dest)
        src_pump = self.get_pump_from_valve_name(src)
        dest_pump = self.get_pump_from_valve_name(dest)

        # Set valves
        src_connect_cmd = self.connect_valve_cmd(
            src, from_port, constants.PUMP_PORT)
        dest_connect_cmd = self.connect_valve_cmd(
            dest, to_port, constants.PUMP_PORT)

        # Execute movement
        src_pump_cmd = {
            "cmd": ("source", 0),
            "volume": volume,
            "speed": mid_pump_speed
        }
        dest_pump_cmd = {
            "cmd": ("sink", 0),
            "volume": volume,
            "speed": mid_pump_speed
        }

        cmds = [
            [src_connect_cmd, dest_connect_cmd],
            [src_pump_cmd, dest_pump_cmd]
        ]
        devices = [
            [src_valve, dest_valve],
            [src_pump, dest_pump]
        ]

        return devices, cmds
