"""
..module:: executor.executor
    :platform: Windows, Unix
    :synopsis: Executes all XDL steps from the given XDL object.
                Steps set up in prepare_for_execution before running.

"""

from typing import Union, Dict, List
from networkx import MultiDiGraph
from commanduinolabware import CommanduinoLabware

# XDL
from xdl.execution.abstract_executor import AbstractXDLExecutor
from xdl.utils.graph import get_graph
from xdl.steps import (
    AbstractDynamicStep,
    Step,
    NON_RECURSIVE_ABSTRACT_STEPS
)
from xdl.readwrite import xdl_to_xml_string

# Relative
from .hardware_mapping import (
    check_hardware_compatibility,
    get_hardware_map,
    map_hardware_to_steps
)
from .implied_steps import (
    set_all_stir_speeds,
    add_reagent_storage_steps,
    add_in_final_shutdown
)
from .implied_properties import (
    add_filter_volumes,
    add_clean_vessel_temps,
    add_all_volumes,
    assign_background_readings_callback,
)
from .filter_dead_volume import (
    confirm_dead_volume_handling_behaviour,
    confirm_dead_volume_solvents,
    add_implied_add_dead_volume_steps,
    add_implied_remove_dead_volume_steps,
    add_filter_inert_gas_connect_steps
)
from .optimize import (
    remove_pointless_dry_return_to_rt,
    optimize_separation_steps,
    tidy_up_procedure
)
from .graph import (
    hardware_from_graph,
    graph_hash
)
from .utils import add_default_ports_to_step
from .cleaning import (
    add_cleaning_steps,
    add_vessel_cleaning_steps,
    verify_cleaning_steps,
    get_cleaning_schedule,
)
from .errors import XDLNoSolventsError
from .validation import check_enough_buffer_flasks, validate_ports
from ..constants import (
    FILTER_DEAD_VOLUME_INERT_GAS_METHOD,
    FILTER_DEAD_VOLUME_LIQUID_METHOD,
)
from ..steps import CleanBackbone
from ..utils.execution import (
    get_chempiler,
)

class ChemputerExecutor(AbstractXDLExecutor):

    _graph = None

    """Class to execute XDL objects. To execute first call prepare_for_execution
    then execute.

    Args:
        xdl (XDL): XDL object to execute.

    Inherits:
        AbstractXDLExecutor: Generic XDL Executor class
    """

    def _graph_hash(self, graph: MultiDiGraph = None):
        """Override default hash with Chemputer specific graph hash."""
        if graph is None:
            graph = self._graph
        return graph_hash(graph)

    def add_internal_properties(
        self, graph: MultiDiGraph, steps: List[Step]
    ) -> None:
        """Recursively add internal properties to all steps and substeps in
        given list of steps. This is used instead of AbstractXDLExecutor method
        as default ports need to be added just before internal properties.

        Args:
            steps (List[Step]): List of steps to add internal properties to.
        """

        # Iterate through each step
        for step in steps:
            # Have to add default ports here, as they alter the steps list so
            # step list update needs to happen before adding internal properties
            # to substeps.
            add_default_ports_to_step(graph, step)

            # Prepare the step for execution
            step.on_prepare_for_execution(graph)

            # Special case for Dynamic steps
            if isinstance(step, AbstractDynamicStep):
                step.prepare_for_execution(graph, self)

            # If the step has children, add internal properties to all children
            if 'children' in step.properties:
                self.add_internal_properties(graph, step.children)

            # Recursive steps, add internal proerties to all substeps
            if not isinstance(step, NON_RECURSIVE_ABSTRACT_STEPS):
                self.add_internal_properties(graph, step.steps)

    #####################
    # ADD IMPLIED STEPS #
    #####################

    def _add_implied_steps(self, interactive: bool = True) -> None:
        """Add extra steps implied by explicit XDL steps.
        These steps may be cleaning or transfer steps that should be expected
        but not explicitly defined by the user.

        Args:
            interactive (bool, optional): Ask the user for input on step
                                        information. Defaults to True.
        """

        # Add steps to deal with dead volume in the tubing after Filter steps
        self._add_filter_dead_volume_handling_steps(interactive=interactive)

        # Automatically add cleaning steps
        if self._auto_clean:
            # Check there are cleaning solvents available
            cleaning_solvents = get_cleaning_schedule(self._xdl)
            if cleaning_solvents[0] is None:
                raise XDLNoSolventsError(
                    'No solvents found in graph for cleaning'
                )

            # Add steps for cleaning vessels
            add_vessel_cleaning_steps(
                self._xdl, self._graph_hardware, interactive)
            self.add_internal_properties(self._graph, self._xdl.steps)

            # Add steps to clean the backbone of the Chemputer
            add_cleaning_steps(self._xdl)
            self.add_internal_properties(self._graph, self._xdl.steps)

            # Interactive mode, ask the user for more information
            if interactive:
                # Ask the user to verify solvents used in cleaning
                verify = None
                while verify not in ['y', 'n', '']:
                    verify = input(
                        'Verify solvents used in backbone and vessel \
    cleaning? (y, [n])\n')

                # Verify the cleaning steps
                if verify == 'y':
                    verify_cleaning_steps(self._xdl)

        # Add steps for dealing with reagent storage
        add_reagent_storage_steps(
            self._graph, self._xdl.steps, self._xdl.reagents)

        # Add steps for adding reagents at the last minute
        # NOTE: This has been removed as noone ever used it and it isn't part of
        # the XDL standard.
        # add_reagent_last_minute_addition_steps(
        #     self._graph, self._xdl.steps, self._xdl.reagents)

        # Set stir speeds of stirrers to default at start of procedure
        set_all_stir_speeds(self._xdl.steps)

    def _add_filter_dead_volume_handling_steps(
        self, interactive: bool = True
    ) -> None:
        """Add steps to handle the filter dead volume. This can be handled in
        two ways determined by the XDL object's filter_dead_volume_method
        attribute (default is 'solvent', alternative is 'inert_gas').

        'solvent' means before liquid is added to the filter, the bottom is
        filled  up with a solvent specified in the <Synthesis> tag of the XDL.
        Before liquid is removed from the filter, the solvent in the bottom is
        removed first.

        'inert_gas' means that when not connected to the vacuumm, the bottom of
        the flask is connected to a stream of inert gas that keeps the liquid in
        the top part of the filter where it is.

        Args:
            interactive (bool, optional) Ask the user for input on step
                                        information. Defaults to True
        """

        # Ask the user to confirm actions for ahndling dead volumes
        if interactive:
            self._filter_dead_volume_method =\
                confirm_dead_volume_handling_behaviour(
                    self._filter_dead_volume_method)

        # Add Filter step using Inert Gas
        if (self._filter_dead_volume_method
                == FILTER_DEAD_VOLUME_INERT_GAS_METHOD):
            add_filter_inert_gas_connect_steps(self._graph, self._xdl.steps)

        # Add Filter step using solvent
        elif (
            self._filter_dead_volume_method == FILTER_DEAD_VOLUME_LIQUID_METHOD
        ):
            self._add_filter_liquid_dead_volume_steps()

            # Ask the user to confirm solvent choice
            if interactive:
                confirm_dead_volume_solvents(self._xdl)

    def _add_filter_liquid_dead_volume_steps(self) -> None:
        """Using 'solvent' method for handling filter dead volume, add
        AddFilterDeadVolume steps and RemoveFilterDeadVolume steps at
        appropriate places to deal with the filter dead volume.
        """

        # Add steps using solvent to clear dead volume
        add_implied_add_dead_volume_steps(
            self._graph, self._graph_hardware, self._xdl)
        self.add_internal_properties(self._graph, self._xdl.steps)

        # Add steps to remove the dead volume
        add_implied_remove_dead_volume_steps(
            self._graph, self._graph_hardware, self._xdl)
        self.add_internal_properties(self._graph, self._xdl.steps)

    ##################
    # PUBLIC METHODS #
    ##################

    def prepare_block_for_execution(
        self, graph_file: Union[str, Dict], block: List[Step]
    ) -> None:
        """Prepare block of AbstractDynamicStep for execution

        Args:
            graph_file (Union[str, Dict]): Path to graph file. May be GraphML
                file, JSON file with graph in node link format, or dict
                containing graph in same format as JSON file.
        """

        # Graph is not a Networkx graph yet, obtain it
        if not type(graph_file) == MultiDiGraph:
            self._graph = get_graph(graph_file)

        # Graph is already Networkx object, proceed
        else:
            self._graph = graph_file

        # Get the hardware from the graph
        self._graph_hardware = hardware_from_graph(self._graph)

        # Add all internal properties to steps
        self.add_internal_properties(self._graph, steps=block)

        # Validate all ports for each step
        validate_ports(self._graph, block)

        # Convert implied properties to concrete values.
        remove_pointless_dry_return_to_rt(steps=block)

        # Optimise the Separation steps
        optimize_separation_steps(steps=block)

        # Set all stirring rates for each Step
        set_all_stir_speeds(steps=block)

        # Add all internal properties to steps
        self.add_internal_properties(self._graph, steps=block)

    def prepare_for_execution(
        self,
        graph_file: Union[str, Dict],
        interactive: bool = True,
        save_path: str = '',
        sanity_check: bool = True,
        auto_clean: bool = False,
        filter_dead_volume_method: str = 'solvent',
        filter_dead_volume_solvent: str = None,
        organic_cleaning_solvent: str = None,
        hardware_map: List[Dict] = None,
        testing: bool = False,
        device_modules=[],
        full_procedure: bool = True,
    ) -> None:
        """Prepare the XDL for execution on a Chemputer corresponding to the
        given graph.
        Any one of graphml_file, json_data, or json_file must be given.

        Args:
            graph_file (Union[str, Dict]): Dictionary representing graph or
                                            filepath to graph.

            interactive (bool, optional): Prompt user to confirm certain steps.
                                            Defaults to True.

            save_path (str, optional): Path to save any output files to.
                                        Defaults to ''.

            sanity_check (bool, optional): Perform sanity checks on XDL steps.
                                            Defaults to True.

            auto_clean (bool, optional): Automatically determine cleaning steps
                                            for the platform. Defaults to True.

            filter_dead_volume_method (str, optional): How to filter the dead
                                            volume in Filter steps.
                                            Defaults to 'solvent'.

            filter_dead_volume_solvent (str, optional): Solvent to use if
                                            filter_dead_volume_method
                                            is set to solvent. Defaults to None.

            organic_cleaning_solvent (str, optional): Which organic solvent to
                                            use for Cleaning steps.
                                            Defaults to None.

            hardware_map (List[Dict], optional): Specic mapping of hardware IDs
                                            in XDL file to those of the graph.

            testing (bool, optional): Testing run. Defaults to False.

        Raises:
            XDLError: Missing the required number of Buffer flasks
        """
        self.add_process_steps(
            graph_file,
            interactive=interactive,
            save_path=save_path,
            sanity_check=sanity_check,
            auto_clean=auto_clean,
            filter_dead_volume_method=filter_dead_volume_method,
            filter_dead_volume_solvent=filter_dead_volume_solvent,
            organic_cleaning_solvent=organic_cleaning_solvent,
            hardware_map=hardware_map,
            testing=testing,
            device_modules=device_modules,
            full_procedure=full_procedure,
        )
        self.optimize_and_compile(
            graph_file,
            save_path,
            sanity_check,
            device_modules=device_modules
        )

    def add_process_steps(
        self,
        graph_file: Union[str, Dict],
        interactive: bool = True,
        save_path: str = '',
        sanity_check: bool = True,
        auto_clean: bool = False,
        filter_dead_volume_method: str = 'solvent',
        filter_dead_volume_solvent: str = None,
        organic_cleaning_solvent: str = None,
        hardware_map: List[Dict] = None,
        testing: bool = False,
        device_modules=[],
        full_procedure: bool = True
    ) -> None:
        """Prepare the XDL for execution on a Chemputer corresponding to the
        given graph.
        Any one of graphml_file, json_data, or json_file must be given.

        Args:
            graph_file (Union[str, Dict]): Dictionary representing graph or
                                            filepath to graph.

            interactive (bool, optional): Prompt user to confirm certain steps.
                                            Defaults to True.

            save_path (str, optional): Path to save any output files to.
                                        Defaults to ''.

            sanity_check (bool, optional): Perform sanity checks on XDL steps.
                                            Defaults to True.

            auto_clean (bool, optional): Automatically determine cleaning steps
                                            for the platform. Defaults to True.

            filter_dead_volume_method (str, optional): How to filter the dead
                                            volume in Filter steps.
                                            Defaults to 'solvent'.

            filter_dead_volume_solvent (str, optional): Solvent to use if
                                            filter_dead_volume_method
                                            is set to solvent. Defaults to None.

            organic_cleaning_solvent (str, optional): Which organic solvent to
                                            use for Cleaning steps.
                                            Defaults to None.

            hardware_map (List[Dict], optional): Specic mapping of hardware IDs
                                            in XDL file to those of the graph.

            testing (bool, optional): Testing run. Defaults to False.

        Raises:
            XDLError: Missing the required number of Buffer flasks
        """
        # The reason for this is that when Chempiler is instantiated during
        # `prepare_for_execution` it does so in simulation mode. Any
        # CommanduinoLabware devices will initialise the CommanduinoLabware
        # singleton in simulation mode. Any attempt thereafter to initialise
        # Chempiler (and therefore the CommanduinoLabware singleton) in
        # non-simulation mode will raise an error saying real and simulated
        # devices cannot be mixed. This resets the singleton so that it can
        # be reinitialised within the same script.
        CommanduinoLabware.reset()

        # Set all instance variables
        self._auto_clean = auto_clean
        self._filter_dead_volume_method = filter_dead_volume_method
        self._filter_dead_volume_solvent = filter_dead_volume_solvent
        self._organic_cleaning_solvent = organic_cleaning_solvent

        # Run with no autoclean and interactive mode in testing environment
        if testing:
            self._auto_clean = interactive = False

        # Not prepared for execution yet
        if not self._prepared_for_execution:
            # Load the graph
            self._graph = get_graph(graph_file)
            self._chempiler = get_chempiler(graph_file, device_modules)

            # Load graph, make Hardware object from graph, and map nearest
            # waste vessels to every node.

            # Create hardware objects from graph
            self._graph_hardware = hardware_from_graph(self._graph)

            # Check hardware compatibility
            check_hardware_compatibility(
                self._xdl.hardware, self._graph_hardware)

            # Map graph hardware to steps.
            # _map_hardware_to_steps is called twice so that
            # _xdl.iter_vessel_contents has all vessels to play with
            # during _add_implied_steps.
            # If a specific hardware map is not given, uses the default
            # generated map. Specific maps are used in parallelisation.
            if not hardware_map:
                self.hardware_map = get_hardware_map(
                    self._xdl.hardware, self._graph)
            else:
                self.hardware_map = hardware_map

            map_hardware_to_steps(
                self._graph, self._xdl.steps, self.hardware_map)

            # Check the total number of buffer flasks present in the graph
            # against the number required by the procedure.
            # This is done during sanity checks, however there could be a
            # problem if two steps try to use the same flask as it will not
            # get cleaned inbetween uses.
            # TODO: This check should be extended to make sure that buffer
            # flasks are not being shared between steps, and that if they
            # are appropriate cleaning should take place.
            check_enough_buffer_flasks(self._graph, self._xdl.steps)

            # Add internal properties to each step
            self.add_internal_properties(self._graph, self._xdl.steps)

            # Perform sanity checks if set on each Step
            if sanity_check:
                self.perform_sanity_checks(self._xdl.steps)

            # Validate ports for each step
            validate_ports(self._graph, self._xdl.steps)

            # Add in steps implied by explicit steps.
            self._add_implied_steps(interactive=interactive)

            # Add internal properties to each step
            self.add_internal_properties(self._graph, self._xdl.steps)

            # Perform sanity checks if set on each Step
            if sanity_check:
                self.perform_sanity_checks(self._xdl.steps)

            # Convert implied properties to concrete values.
            add_clean_vessel_temps(self._xdl.steps)

            # Optimise separation steps
            optimize_separation_steps(self._xdl.steps)

            # Remove pointless steps
            remove_pointless_dry_return_to_rt(self._xdl.steps)

            if full_procedure:
                # Add in the Shutdown step to the end of the Step list
                add_in_final_shutdown(self._xdl.steps)

            else:
                # Remove first CleanBackbone step if XDL is not for full
                # procedure. Paralleliser handles this first step itself,
                # and this step shouldn't be duplicated for multiple
                # parallel blocks
                for i, step in enumerate(self._xdl.steps):
                    if type(step) == CleanBackbone:
                        self._xdl.steps.pop(i)
                        break

            # Assigning callback function for dynamic steps with sensors
            # Feedback
            assign_background_readings_callback(self._xdl.steps)

            if save_path:
                self._xdl.save(save_path)

            # The reason for this is that when Chempiler is instantiated during
            # `prepare_for_execution` it does so in simulation mode. Any
            # CommanduinoLabware devices will initialise the CommanduinoLabware
            # singleton in simulation mode. Any attempt thereafter to initialise
            # Chempiler (and therefore the CommanduinoLabware singleton) in
            # non-simulation mode will raise an error saying real and simulated
            # devices cannot be mixed. This resets the singleton so that it can
            # be reinitialised within the same script.
            CommanduinoLabware.reset()

    def optimize_and_compile(
        self,
        graph_file: Union[str, Dict],
        save_path: str = '',
        sanity_check: bool = True,
        device_modules=[],
    ):

        # Load the graph
        if self._graph is None:
            self._graph = get_graph(graph_file)
            self._chempiler = get_chempiler(graph_file, device_modules)

        # Load graph, make Hardware object from graph, and map nearest
        # waste vessels to every node.

        # Create hardware objects from graph
        self._graph_hardware = hardware_from_graph(self._graph)

        # Check hardware compatibility
        check_hardware_compatibility(self._xdl.hardware, self._graph_hardware)

        self.add_internal_properties(self._graph, self._xdl.steps)

        # These have to come here as they need the exact knowledge of vessel
        # contents provided by iter_vessel_contents. However this requires that
        # internal props have been added and the procedure is in as complete a
        # state as possible to get accurate vessel volumes, hence why this is
        # here rather than nearer the beginning of the compilation sequence.
        #
        # In the future it would be good if iter_vessel_contents could work on
        # high level steps that have not been compiled, so these properties
        # could be added in add_process_steps.
        add_all_volumes(self._graph, self._graph_hardware, self._xdl.steps)
        add_filter_volumes(
            self._graph, self._graph_hardware, self._xdl.steps)

        # The updates to volume properties in
        # add_filter_volumes means that steps lists may have been regenerated
        # and new steps may need internal properties added.
        self.add_internal_properties(self._graph, self._xdl.steps)

        # Perform sanity checks if set on each Step
        if sanity_check:
            self.perform_sanity_checks(self._xdl.steps)

        # Optimise procedure.
        tidy_up_procedure(
            self._graph,
            self._graph_hardware,
            self._chempiler,
            self._xdl.steps
        )

        # Prepared for execution now
        self._prepared_for_execution = True

        # Saving here as this method not currently called from XDL object, only
        # called directly from executor so saving not done in XDL method.
        # This results in a double save when this is called from
        # XDL.prepare_for_execution but that doesn't really matter.
        if save_path:
            self.save_xdlexe(save_path)

        # The reason for this is that when Chempiler is instantiated during
        # `prepare_for_execution` it does so in simulation mode. Any
        # CommanduinoLabware devices will initialise the CommanduinoLabware
        # singleton in simulation mode. Any attempt thereafter to initialise
        # Chempiler (and therefore the CommanduinoLabware singleton) in
        # non-simulation mode will raise an error saying real and simulated
        # devices cannot be mixed. This resets the singleton so that it can
        # be reinitialised within the same script.
        CommanduinoLabware.reset()

    def save_xdlexe(self, save_path: str):
        """Save XDLEXE file to given save path. This should be called after
        ``prepare_for_execution``.
        """
        with open(save_path, 'w') as fd:
            fd.write(
                xdl_to_xml_string(
                    self._xdl,
                    graph_hash=self._graph_hash(),
                    full_properties=True,
                    full_tree=True
                )
            )
