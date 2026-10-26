from typing import Tuple, Any, Dict, List
from xdl.platforms.abstract_platform import AbstractPlatform
from networkx import MultiDiGraph
import abc
import time
import os
import appdirs
import socketio
import logging
import json
import secrets
from threading import Thread
from ..constants import CHEMIFY_API_URL
from ..xdl import XDL
from ..utils.graph import get_graph
from ..steps import NON_RECURSIVE_ABSTRACT_STEPS, Step
from ..errors import XDLError

#: socketio Client global variable
sio = socketio.Client()

def get_xdl_logger(logging_id: str, log_file: str) -> logging.Logger:
    """Get XDL logger that sends output to log_file.

    Args:
        logging_id (str): Unique ID for logger.
        log_file (str): File to send logs to.

    Returns:
        logging.Logger: Logger that sends logs to log_file.
    """
    xdl_logger = logging.getLogger(f'xdl-{logging_id}')

    xdl_handler = logging.FileHandler(log_file)
    xdl_formatter = logging.Formatter('XDL: %(message)s')
    xdl_handler.setFormatter(xdl_formatter)
    xdl_handler.setLevel(logging.INFO)

    xdl_logger.setLevel(logging.INFO)
    xdl_logger.addHandler(xdl_handler)

    return xdl_logger

def step_is_confirm(step: Step):
    """Return True, if step is Confirm, or is a wrapper around Confirm.

    Args:
        step (Step): Step to check whether it is Confirm or not.

    Returns:
        bool: True if step is Confirm or step is a simple wrapper around
            Confirm, otherwise False.
    """
    # Step is Confirm, return True
    if step.name == 'Confirm':
        return True

    # Step is base step and not Confirm, return False
    elif isinstance(step, NON_RECURSIVE_ABSTRACT_STEPS):
        return False

    # Step has 1 substep and it is a Confirm step, return True
    elif len(step.steps) == 1 and step.steps[0].name == 'Confirm':
        return True

    # Default to False
    return False

class XDLExecutionClient(object):
    """Abstract class for a XDL execution client. The purpose of any subclass of
    this class is to be able to connect to ChemifyAPI, and integrate into the
    execution mode of ChemIDE. Regardless of the platform, as long as the
    abstract methods here are implemented, the execution client should work with
    ChemifyAPI / ChemIDE.

    To use a XDL execution client run a script like this:
        ```
        # Localhost or real ChemifyAPI address
        chemify_api_address = 'http://localhost:5000'

        # Instantiate client with ChemifyAPI address
        client = SpecificPlatformExecutionClient(chemify_api_address)

        # Register client with socketio callbacks defined here.
        register_execution_client(client)

        # Run client
        client.run()
        ```
    Args:
        address (str): Address of ChemifyAPI.

    Abstract Methods:
        get_platform_controller: Return platform controller given graph.
        emergency_stop: Stop platform controller as fast as possible.
    """

    ####################
    # Static Variables #
    ####################

    #: Return value if step throws an error
    STEP_FAILED: int = 0

    #: Return value if step encounters stop flag
    STEP_STOPPED: int = 1

    #: Return value if step encounters pause flag
    STEP_PAUSED: int = 2

    #: Return value if step completes without error
    STEP_COMPLETED: int = 3

    #: Time interval in seconds at which to read logs during execution.
    READ_LOGS_INTERVAL: int = 2

    ######################
    # Instance variables #
    ######################

    #: Unique key used to connect to ChemifyAPI / ChemIDE.
    execution_key: str = ''

    #: Address of ChemifyAPI
    _address: str = ''

    #: If False instantiate platform controller in simulation mode, otherwise
    #: instantiate platform controller for physical execution.
    _simulation: bool = False

    #: Logger for simple logging to terminal. Not used for sending logs to
    #: ChemifyAPI / ChemIDE.
    _logger: logging.Logger = None

    #: Platform controller object used to actually operate platform.
    _platform_controller: Any = None

    #: Loaded graph object.
    _graph: MultiDiGraph = None

    #: XDL object loaded from xdlexe. All steps executed come from
    #: self.xdl.steps
    _xdl: XDL = None

    #: Summary of XDL given to app containing, for every step, a dict specifying
    #: UUID, human readable and a bool showing whether the step is Confirm.
    _xdl_summary: List[Dict] = []

    #: File to send execution logs to. These logs are sent back to ChemifyAPI
    #: and ChemIDE and should be logs from XDL and the platform controller, not
    #: just internal logs from the execution client.
    _log_file: str = ''

    #: Dict of { step_uuid: step_logs }
    _logs: Dict[str, str] = {}

    #: List of step UUIDs for steps that have been successfully completed. Used
    #: to know which steps to skip when resuming after a pause.
    _completed_substeps: List[str] = []

    #: Flag used to know if a step is in the process of finding its resume
    #: point. I.e. while finding resume point don't log anything.
    _resuming: bool = False

    #: Flag used to tell execution to stop at next opportunity. Stopping is only
    #: possible between base steps.
    _stop: bool = False

    #: Flag used to tell execution to pause at next opportunity. Pausing is only
    #: possible between base steps.
    _pause: bool = False

    #: UUID of step paused. Used to know whic step to execute on resume.
    _pause_uuid: str = ''

    #: Flag used to tell log reading thread to stop reading logs and allow
    #: itself to be joined.
    _stop_reading_logs: bool = False

    #: Logger to send XDL logs to self.log_file
    _xdl_logger: logging.Logger = None

    #: Platform object for platform being targeted by execution client
    _platform: AbstractPlatform = None

    def __init__(
        self, address: str = CHEMIFY_API_URL, simulation: bool = False
    ) -> None:
        # Generate unique execution key for instance to connect to ChemifyAPI
        self.execution_key = secrets.token_urlsafe()

        # Set address for use in self.run to connect to ChemifyAPI
        self._address = address

        # Set simulation flag to specify what mode to instantiate platform
        # controller in.
        self._simulation = simulation

        # Initialise internal logging (not sent to ChemifyAPI)
        self._logger = logging.getLogger('xdl-execution-client')
        self._logger.setLevel(logging.INFO)
        self._logger.addHandler(logging.StreamHandler())

        # Intialise execution logging (sent to ChemifyAPI)
        self._log_file = self._get_log_file()
        self._xdl_logger = get_xdl_logger(self.execution_key, self._log_file)

        # Initialize platform
        self._platform = self._get_platform()

        register_execution_client(self)

        sio.connect(self._address)

    ####################
    # Abstract Methods #
    ####################

    @abc.abstractmethod
    def _get_platform_controller(
        self, graph: str, simulation: bool = False
    ) -> Tuple[Any, str]:
        """Get platform controller object to actually operate platform with.
        Must be implemented by any subclass.

        Args:
            graph (str): Node link JSON graph to use when instantiating
                platform controller.
            simulation (bool): If True, instantiate platform controller in
                simulation mode.

        Returns:
            Tuple[Any, str]: Tuple of (platform_controller, error). If error
                occurs during instantiation return (None, error_msg). If no
                error occurs return (platform_controller, '')
        """
        return None, ''

    @abc.abstractmethod
    def _get_platform(self) -> AbstractPlatform:
        return None

    @abc.abstractmethod
    def emergency_stop(self) -> None:
        """Stop platform controller as fast as possible. Called when user
        presses "Emergency Stop" button in ChemIDE.
        """
        self._pause = True

    @abc.abstractmethod
    def _on_disconnect(self) -> None:
        """Run code when app disconnects from execution client."""
        pass

    ##################
    # Public Methods #
    ##################

    def bind_platform_controller(self, platform_controller: Any) -> None:
        """Bind platform controller to the execution client. The reason for this
        functionality is to allow the execution client to be used in 2 ways.

        1. Controlled: The execution client creates its own platform
           controller objects, uses them internally, and keeps them hidden from
           the user. This allows the execution client to be simply launched by
           running a script.
        2. Uncontrolled: The execution client is launched by the user inside a
           script or iPython / Jupyter Notebook environment. They then
           instantiate their own platform controller object, and bind this to
           the execution client. The execution client will then use this, and
           not make any platform controller objects itself. This is necessary
           if both platform controller and xdl execution clients need to be used
           and is useful in the case the user wants full control of the platform
           controller.

        Args:
            platform_controller (Any): Platform controller to bind to execution
                client. It is up to the user to make sure that this object has
                the correct graph and setup for the experiment being performed.
        """
        self._platform_controller = platform_controller
        self._platform_controller.run_execution_client(
            execution_key=self.execution_key,
            api_url=self._address,
        )
        self._bound_platform_controller = True

    def unbind_platform_controller(self) -> None:
        """Unbind bound platform controller so that execution client can revert
        to controlled mode and make its own platform controller objects.
        """
        self._platform_controller = None
        self._bound_platform_controller = False

    def execute_step_device(self, graph, step_name, properties) -> None:
        """Execute command given by live control step device.

        Args:
            graph (str): JSON string graph
            step_name (str): Name of step to be executed.
            properties (Dict[str, Any]): Properties to instantiate step with.
        """
        self._logger.info(
            f'Executing step: {step_name} {properties}\n')

        graph = get_graph(json.loads(graph))

        # If client not bound to platform controller, create temporary instance
        # just for executing this step.
        if not self._platform_controller:
            platform_controller, error = self._get_platform_controller(
                graph, self._simulation)
            if error != '':
                raise XDLError(error)
        else:
            platform_controller = self._platform_controller

        # Instantiate step
        step_class = self._platform.step_library[step_name]
        step = step_class(**properties)

        # Compile step
        executor = self._platform.executor()
        executor._graph = graph
        executor.add_internal_properties(graph=graph, steps=[step])
        executor.perform_sanity_checks(steps=[step], graph=graph)

        # Execute step
        executor.execute_step(platform_controller, step)

    def run(self) -> None:
        """Connect to ChemifyAPI and wait for messages."""
        sio.wait()

    def load_experiment(self, graph: str, xdlexe: str) -> None:
        """Load platform controller object and xdlexe. Emit result.

        Args:
            graph (str): Node link JSON graph to use when instantiating
                platform controller.
            xdlexe (str): xdlexe str compiled using graph.

        Emits:
            'execlient-loaded-experiment', {
                error (str): Blank string if experiment loaded
                    successfully otherwise error message.
                xdlexe_summary (List[Dict]): List of all steps in xdlexe with
                    a Dict containing UUID, human readable and confirm flag for
                    every step.
                execution_key (str): Instance execution key.
            }
        """
        # Load graph
        self._graph = get_graph(json.loads(graph))

        # Load xdlexe
        error = self._load_xdlexe(xdlexe)

        # Run simulation to check no runtime errors will be encountered
        if not error:
            error = self._run_simulation()

        # Instantiate platform controller. self._simulation flag used to allow
        # simulation mode to be used from the command line when testing.
        if not error and not self._bound_platform_controller:
            self._platform_controller, error = self._get_platform_controller(
                self._graph, simulation=self._simulation)

        # Emit result of loading experiment
        sio.emit('execlient-loaded-experiment', {
            'error': error,
            'execution_key': self.execution_key,
            'xdlexe_summary': self._xdl_summary,
        })
        self._logger.info('Loaded experiment.')

    def execute_step(self, step_uuid: str, resume: bool = False):
        """Execute step corresponding to given step UUID. Also start logging
        thread and emit logs at regular interval.

        Args:
            step_uuid (str): UUID of step to execute. Must be step in self.xdl
            resume (bool): If True, resuming after pause so don't do or log
                anything until reached step at which pause occurred.

        Emits:
            'execlient-paused-step': {
                execution_key (str): Instance execution key.
                uuid (str): UUID of step paused.
            }
            'execlient-stopped-step': {
                execution_key (str): Instance execution key.
                uuid (str): UUID of step stopped.
            }
            'execlient-step-complete': {
                failed (bool): True if error occurred during execution,
                    otherwise False.
                execution_key (str): Instance execution key.
                uuid (str): UUID of step executed.
            }
        """
        # Reset flags
        self._stop, self._pause = False, False
        self._stop_reading_logs = False

        # If starting from scratch and not resuming, clear log file,
        #  _completed_substeps list and self._logs[step_uuid].
        if not self._resuming:
            self._reset_log_file()
            self._completed_substeps = []
            self._logs[step_uuid] = ''

        # Start log reading thread
        self._log_reading_thread = self._read_logs_thread(step_uuid)
        self._log_reading_thread.start()

        # Check platform controller instantiated.
        if not self._platform_controller:
            self._logger.info(
                "Can't execute. Platform controller not initialised.")
            return

        # Get step object to instantiate.
        step = [step for step in self._xdl.steps if step.uuid == step_uuid][0]

        # Initialise failed result.
        failed = False

        # Go through all substeps and recursively execute base steps.
        for substep in step.steps:

            # Execute substep
            res = self._execute_substep(substep)

            # If substep failed, set failed to True, stop execution and emit
            # result.
            if res == self.STEP_FAILED:
                failed = True
                break

            # If substep encountered stop or pause flag, stop execution and emit
            # appropriate signal.
            elif res in [self.STEP_STOPPED, self.STEP_PAUSED]:

                # Reset flags
                self._stop, self._pause = False, False

                # Store UUID of step for resuming from pause.
                if res == self.STEP_PAUSED:
                    self._pause_uuid = step_uuid

                # Join log reading thread.
                self._stop_reading_logs = True
                self._log_reading_thread.join()

                # Emit signal
                signal = 'execlient-paused-step'
                if res == self.STEP_STOPPED:
                    signal = 'execlient-stopped-step'
                sio.emit(signal, {
                    'uuid': step_uuid,
                    'execution_key': self.execution_key,
                })
                return

        # Execution complete, reset flags
        self._stop, self._pause = False, False

        # Join log reading thread.
        self._stop_reading_logs = True
        self._log_reading_thread.join()

        # Emit complete signal
        sio.emit('execlient-step-complete', {
            'failed': failed,
            'execution_key': self.execution_key,
            'uuid': step_uuid,
        })

    def stop(self):
        """Stop execution gracefully by setting self._stop to True. Stops
        execution at end of current base step.
        """
        self._logger.info('Stopping...')
        self._stop = True

    def pause(self):
        """Stop execution gracefully by setting self._pause to True. Stops
        execution at end of current base step.
        """
        self._logger.info('Pausing...')
        self._pause = True

    def resume(self):
        """Resume execution from point at which it was paused."""
        self._resuming = True
        self._logger.info('Resuming...')
        self.execute_step(self._pause_uuid)

    def disconnect(self) -> None:
        """Called when app disconnects from execution client."""
        self._on_disconnect()
        self.reset()

    ###################
    # Private Methods #
    ###################

    def _run_simulation(self) -> str:
        """Run simulation using self._xdl and self._graph. Return empty string
        if simulation successful or error message if an error occurs.

        Returns
            str: Empty string if simulation successful or error message if an
                error occurs.
        """
        if not self._bound_platform_controller:
            simulation_platform_controller, error =\
                self._get_platform_controller(self._graph, simulation=True)
        else:
            simulation_platform_controller = self._platform_controller
        if not error:
            try:
                confirm_step_uuids = [
                    step['uuid'] for step in self._xdl_summary
                    if step['confirm']
                ]
                for step in self._xdl.steps:
                    if step.uuid not in confirm_step_uuids:
                        self._xdl.executor.execute_step(
                            simulation_platform_controller, step)
            except Exception as e:
                error = str(e)
        return error

    def _load_xdlexe(self, xdlexe):
        """Load xdlexe.

        Args:
            xdlexe (str): xdlexe str to load.
        """
        try:
            self._xdl = XDL(xdlexe)
            self._xdl.executor.logger = self._xdl_logger
            self._xdl.logger = self._xdl_logger
            assert self._xdl.compiled is True
            self._xdl_summary = self._get_xdl_summary()
            error = ''
        except XDLError as e:
            error = str(e)
        self._logger.info('Loaded xdlexe.')
        return error

    def _get_xdl_summary(self) -> List[Dict]:
        """Generate summary of all steps in XDL with enough information for
        ChemIDE to display steps in UI.

        Returns:
            List[Dict]: List of dicts containing summary of every step in
               self.xdl.steps. Each dict is  of the format {
                   uuid (str): UUID of step,
                   humanReadable (str): Human readable sentence describing step.
                   confirm (bool): True if step is a Confirm step, or a simple
                       wrapper around True, otherwise False.
               }
        """
        summary = []
        for step in self._xdl.steps:
            summary.append({
                'uuid': step.uuid,
                'humanReadable': step.human_readable(),
                'confirm': step_is_confirm(step)
            })
        return summary

    def _get_log_file(self) -> str:
        """Get path to log file for temporarily storing execution logs. Make any
        directories necessary to make file immediately writable.

        Returns (str): Path to log file for temporarily storing execution logs.
        """
        logs_folder = appdirs.user_data_dir('xdl-execlient')
        os.makedirs(logs_folder, exist_ok=True)
        return os.path.join(
            logs_folder,
            self.execution_key + '.txt'
        )

    def _reset_log_file(self) -> None:
        """Clear log file."""
        with open(self._log_file, 'w') as fd:
            fd.write('')

    def _read_logs(self) -> str:
        """Read log file and return contents.

        Returns:
            str: Contents of self._log_file
        """
        with open(self._log_file) as fd:
            logs = fd.read()
        return logs

    def _read_logs_thread(self, uuid: str) -> Thread:
        """Return thread for reading logs at a regular interval.

        Args:
            uuid (str): UUID of step currently being executed.

        Returns:
            Thread: Thread to read execution logs at regular interval and store
                result in self._logs[uuid].
        """
        return Thread(target=self._read_logs_target, args=(uuid,))

    def _read_logs_target(self, uuid: str) -> None:
        """Target function of _read_logs_thread. Keeps reading logs indefinitely
        at time interval specified by self.READ_LOGS_INTERVAL until
        self._stop_reading_logs flag is found to be True. Logs are stored in
        self._logs[uuid] when they are read, and also emitted to ChemifyAPI.

        Args:
            uuid (str): UUID of step currently being executed.

        Emits:
            'execlient-logs', {
                logs (str): Logs of step currently being executed.
                execution_key (str): Instance execution key.
                uuid (str): UUID of step currently being executed.
            }
        """
        while True:
            # Pause between reads
            time.sleep(self.READ_LOGS_INTERVAL)

            # Read logs
            self._logs[uuid] = self._read_logs()

            # Emit latest logs
            sio.emit('execlient-logs', {
                'logs': self._logs[uuid],
                'execution_key': self.execution_key,
                'uuid': uuid,
            })

            # Check if should stop logging, and if yes, return
            if self._stop_reading_logs:
                return

    def _execute_substep(self, substep: Step) -> int:
        """Recursively execute given step and return result code.

        Args:
            substep (Step): Step to recursively execute.

        Returns:
            int: Returns one of the following.
                self.STEP_COMPLETED - Step completed successfully.
                self.STEP_FAILED - Step threw an error.
                self.STEP_STOPPED - Step encountered stop flag.
                self.STEP_PAUSED - Step encountered pause flag.
        """
        # If resuming and substep has already been executed (UUID in
        # self._completed_substeps) then just return self.STEP_COMPLETED
        # without doing or logging anything.
        if self._resuming and substep.uuid in self._completed_substeps:
            return self.STEP_COMPLETED

        # Step is executable step, execute and return result.
        if isinstance(substep, NON_RECURSIVE_ABSTRACT_STEPS):
            res = self._execute_base_step(substep)

            # Step completed successfully, append step to
            # self._completed_substeps.
            if res == self.STEP_COMPLETED:
                self._completed_substeps.append(substep.uuid)
            return res

        # Step containg substeps. Recursively execute substeps.
        else:
            # Only log this while not resuming otherwise you'll end up with
            # duplicate log messages on resume.
            if not self._resuming:
                self._xdl_logger.info(f'\n{substep.name}')

            # Go through substeps step list and execute each step.
            for subsubstep in substep.steps:
                res = self._execute_substep(subsubstep)

                # Return result if result is not self.STEP_COMPLETED
                if res != self.STEP_COMPLETED:
                    return res

                # Step completed successfully, add to self._completed_substeps.
                else:
                    self._completed_substeps.append(subsubstep.uuid)

        # Substep completed successfully, append to self._completed_substeps and
        # return.
        self._completed_substeps.append(substep.uuid)

        return self.STEP_COMPLETED

    def _execute_base_step(self, base_step: Step) -> int:
        """Execute AbstractBaseStep, AbstractDynamicStep or AbstractAsyncStep.
        Return result of execution.

        Args:
            base_step (Step): Step to execute.

        Returns:
            int: Returns one of the following.
                self.STEP_COMPLETED - Step completed successfully.
                self.STEP_FAILED - Step threw an error.
                self.STEP_STOPPED - Step encountered stop flag.
                self.STEP_PAUSED - Step encountered pause flag.
        """
        # If step is executing then resume point has been found. Reset flag.
        self._resuming = False

        # This is just here for debugging, so that steps don't execute
        # instantaneously and pause / stop functionality etc can be tested.
        time.sleep(1)

        # Stop flag is True, return self.STEP_STOPPED to tell self.execute_step
        # to stop executing.
        if self._stop is True:
            return self.STEP_STOPPED

        # Pause flag is True, return self.STEP_PAUSED to tell self.execute_step
        # to stop executing.
        elif self._pause is True:
            return self.STEP_PAUSED

        # Execute step
        else:
            try:
                self._xdl.executor.execute_step(
                    self._platform_controller, base_step)

            # Error occurred during step execution, return self.STEP_FAILED.
            except Exception:
                return self.STEP_FAILED

        # Step executed successfully, return self.STEP_COMPLETED.
        return self.STEP_COMPLETED

    def _reset(self):
        """Reset state of execution client. Drop platform controller and current
        xdl and reset all flags.
        """
        self._logger.info('Resetting...')
        self._xdl, self._graph, self._platform_controller = None, None, None
        self._pause, self._stop = False, False
        self._stop_reading_logs = False


client = None

def register_execution_client(execution_client: XDLExecutionClient) -> None:
    """This is necessary so that a subclass of XDLExecutionClient can be defined
    in another file, and a client instance instantiated there, and for that
    instance to then be available to the socket.io handlers here.

    Usage:
        ```
        from xdl.execution.client import (
            XDLExecutionClient, register_execution_client)

        class MyExecutionClient(XDLExecutionClient):
            ...

        client = MyExecutionClient('http://localhost:5000')
        register_execution_client(client)
        ```

    Args:
        execution_client (XDLExecutionClient): Execution client to register
            with socket.io handlers.
    """
    global client
    client = execution_client


@sio.event
def connect():
    """Handle initial connection to server.
    Emit registration signal with execution key.
    """
    print(f'Connecting to server at {client._address} '  # noqa: T001
          'with execution key {client.execution_key}')
    sio.emit('xdl-platform-execlient-register',
             {'execution_key': client.execution_key})

@sio.on('execlient-registered')
def on_execlient_registered(data):
    print('XDL platform execution client connected to server.\n')  # noqa: T001

@sio.on('app-load-experiment')
def on_load_experiment(data):
    """Load platform controller and xdlexe."""
    client.load_experiment(graph=data['graph'], xdlexe=data['xdlexe'])

@sio.on('app-execute-step-device')
def on_execute_step_device(data):
    client.execute_step_device(
        graph=data['graph'],
        step_name=data['step_name'],
        properties=data['properties']
    )

@sio.on('app-start-step')
def on_execute(data):
    """Start executing step."""
    client.execute_step(data['uuid'])

@sio.on('app-stop-step')
def on_stop_step(data):
    """Gracefully stop executing current step."""
    client.stop()

@sio.on('app-pause-step')
def on_pause_step(data):
    """Gracefully pause executing current step."""
    client.pause()

@sio.on('app-resume-step')
def on_resume_step(data):
    """Resume executing current step after pause."""
    client.resume()

@sio.on('app-reset')
def on_reset(data):
    """Reset client state."""
    client.reset()

@sio.on('app-connect')
def on_app_connect(data):
    """Return execution key as a way of proving execution client is alive and
    ready to execute.
    """
    sio.emit('execlient-accepted-connection', {
        'execution_key': client.execution_key})

@sio.on('app-disconnect')
def on_app_disconnect(data):
    """Return execution key confirming execution client successfully
    disconnected.
    """
    client.disconnect()

@sio.on('app-emergency-stop')
def on_emergency_stop(data):
    """Stop execution as fast as possible."""
    client.emergency_stop()
