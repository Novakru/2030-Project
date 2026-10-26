"""Tools for initializing Chempiler logging, and for parsing log files."""

from typing import List, Tuple
import logging
import os
import re
from datetime import datetime

def xdl_log_asctime_to_timestamp(xdl_log_line: str) -> float:
    """Convert asctime in XDL logs to timestamp in seconds since epoch.
    For use when parsing log files.

    Args:
        xdl_log_line (str): Line from XDL log file.

    Returns:
        float: Time in seconds since epoch corresponding to asctime in line from
        XDL log file.
    """
    # Can't use datetime.fromisoformat as not compatible with Python 3.6.
    time_str = xdl_log_line.split(';')[0].split(',')[0]
    year = int(time_str[:4])
    month = int(time_str[5:7])
    day = int(time_str[8:10])
    hour = int(time_str[11:13])
    minute = int(time_str[14:16])
    second = int(time_str[17:19])
    dt = datetime(
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
    )
    return dt.timestamp()

def parse_xdl_step_times_from_logs(info_log_file) -> List[Tuple]:
    """Parse info log file and extract start and finish times of all
    executed steps.

    Returns:
        List[Tuple]: List of details of steps that have finished executing
        in format:
        [
            (step_name,
            step_indexes,
            step_human_readable,
            step_start_time,
            step_end_time),
            ...
        ]

        An example tuple would be:
        ('Transfer',
            [0, 1],
            'The contents of reactor was transferred to filter.',
            30,
            200
        )

        ``step_indexes`` shows the nested index of the XDL step, with
        indexes starting at 0 as is the case in the ``xdl`` code, not from
        1 as is the case in the log file.

        ``step_start_time`` and ``step_end_time`` are both in seconds
        relative to ``self.sensor_readings['start_time']``.
    """
    step_times = []

    # Initialize patterns for reading file
    start_step_index_pattern = r'Executing step ([0-9\.]+)'
    end_step_pattern = r'Finished executing step ([0-9\.]+) ([A-Za-z]+)'

    # Dict to store step details so that they can be combined with end
    # times at a later point in the file.
    open_steps = {}

    # Read XDL logs from file
    with open(info_log_file) as fd:
        lines = [
            line.strip()
            for line in fd.readlines()
        ]

    # Go through XDL lines in log file.
    for i, line in enumerate(lines):

        # Step start
        if '; XDL ; Executing step' in line:
            # Extract step details
            step_index_str = re.search(start_step_index_pattern, line)[1]
            step_start_time = xdl_log_asctime_to_timestamp(line)
            human_readable = lines[i + 1]
            step_name = lines[i + 2]

            # Store details of step for combining with end of step later in
            # file.
            open_steps[step_index_str] = {
                'name': step_name,
                'human_readable': human_readable,
                'start_time': step_start_time
            }

        # Step end
        elif '; XDL ; Finished executing step' in line:
            # Get step index and end time
            search = re.search(end_step_pattern, line)
            step_index_str = search[1]
            step_indexes = [int(i) - 1 for i in step_index_str.split('.')]
            step_name = search[2]
            step_end_time = xdl_log_asctime_to_timestamp(line)

            # Get details from start of step
            open_step_details = open_steps[step_index_str]
            step_start_time = open_step_details['start_time']
            step_human_readable = open_step_details['human_readable']

            # Combine all data and add to `step_times`
            step_times.append((
                step_name,
                step_indexes,
                step_human_readable,
                step_start_time,
                step_end_time
            ))

            # Remove open step from dict as it has been closed.
            del open_steps[step_index_str]

    return step_times

class XDLFileFormatter(logging.Formatter):
    """Formatter to remove ANSI codes introduced by user of ``termcolor``.

    Necessary for saving logs to file.
    """
    ansi_re = re.compile(r'\x1b\[[0-9;]*m')

    def format(self, record):
        record.msg = re.sub(self.ansi_re, '', record.msg)
        return logging.Formatter('%(asctime)s ; XDL ; %(msg)s').format(record)

def console_filter(record):
    """Filter for XDL logging. Stops step duration logs being added to the INFO
    and DEBUG logs.
    """
    if record.funcName == 'log_duration':
        return False
    return True

def duration_filter(record):
    if record.funcName != 'log_duration':
        return False
    return True


# Reason for using global variables here is so that repeated calls to
# `logger.addHandler` don't add duplicate handlers. `logger.addHandler` won't
# add a handler if exactly that object is already in the `logger.handlers` list.
xdl_info_fh: logging.FileHandler = None
xdl_debug_fh: logging.FileHandler = None
xdl_duration_fh: logging.FileHandler = None

# Pylabware Log Handlers
# Reasons similar to above for XDL handlers
pylabware_info_fh: logging.FileHandler = None
pylabware_debug_fh: logging.FileHandler = None

def get_logger(exp_name, output_dir, logging_level=logging.INFO):
    logger = logging.getLogger("chempiler")
    logger.setLevel(logging.DEBUG)  # Has to be below DEBUG for video handler
    # remove any default handlers, e.g. from Jupyter
    # see https://github.com/ipython/ipython/issues/8282
    logger.handlers = []

    if output_dir:
        # create file handler which logs all messages
        log_folder = os.path.join(output_dir, "log_files")
        os.makedirs(log_folder, exist_ok=True)

        # add the handlers to the loggers
        logger.addHandler(get_info_file_handler(log_folder, exp_name))
        logger.addHandler(get_debug_file_handler(log_folder, exp_name))

        # Add XDL logging handlers so XDL logs get included in files.
        xdl_logger = logging.getLogger('xdl')

        # Initialize XDL handlers if not already initialized
        if not xdl_debug_fh:
            initialize_debug_xdl_file_handler(log_folder, exp_name)
        if not xdl_info_fh:
            initialize_info_xdl_file_handler(log_folder, exp_name)
        if not xdl_duration_fh:
            initialize_duration_xdl_file_handler(log_folder, exp_name)

        # Add XDL handlers
        if xdl_debug_fh:
            xdl_logger.addHandler(xdl_debug_fh)
        if xdl_info_fh:
            xdl_logger.addHandler(xdl_info_fh)
        if xdl_duration_fh:
            xdl_logger.addHandler(xdl_duration_fh)

        # Get he PyLabware Logger
        pylabware_logger = logging.getLogger("SerialLabware")

        # Set ahndlers if not set already
        if not pylabware_debug_fh:
            initialize_debug_pylabware_handler(log_folder, exp_name)
        if not pylabware_info_fh:
            initialize_info_pylabware_handler(log_folder, exp_name)

        # Attach handlers
        if pylabware_debug_fh:
            pylabware_logger.addHandler(pylabware_debug_fh)
        if pylabware_info_fh:
            pylabware_logger.addHandler(pylabware_info_fh)

    logger.addHandler(get_console_handler(logging_level))

    return logger

def get_video_logger(exp_name, output_dir):
    logger = logging.getLogger("chempiler_video")
    logger.setLevel(5)  # Has to be below DEBUG for video handler
    # remove any default handlers, e.g. from Jupyter
    # see https://github.com/ipython/ipython/issues/8282
    logger.handlers = []

    # create file handler which logs all messages
    log_folder = os.path.join(output_dir, "log_files")
    os.makedirs(log_folder, exist_ok=True)
    logger.handlers.append(
        get_debug_file_handler(log_folder, exp_name, level=5)
    )

    return logger

def get_file_formatter():
    return logging.Formatter(
        "%(asctime)s ; %(levelname)s ; %(module)s ; %(threadName)s ;\
 %(message)s")

def get_pylabware_file_formatter():
    return logging.Formatter('%(asctime)s ; PyLabware ; %(message)s')

def initialize_info_xdl_file_handler(log_folder, exp_name):
    """Initialize handler for XDL info level logs. Reason for using global
    variable is so that the handler doesn't get readded to the XDL logger with
    repeated calls to logger.addHandler.
    """
    global xdl_info_fh
    xdl_info_fh = logging.FileHandler(
        filename=os.path.join(log_folder, "{0}_info.log".format(
            exp_name)), encoding='utf-8')
    xdl_info_fh.setLevel(logging.INFO)
    xdl_info_fh.setFormatter(XDLFileFormatter())
    xdl_info_fh.addFilter(console_filter)

def initialize_debug_xdl_file_handler(log_folder, exp_name):
    """Initialize handler for XDL debug level logs. Reason for using global
    variable is so that the handler doesn't get readded to the XDL logger with
    repeated calls to logger.addHandler.
    """
    global xdl_debug_fh
    xdl_debug_fh = logging.FileHandler(
        filename=os.path.join(log_folder, "{0}_debug.log".format(
            exp_name)), encoding='utf-8')
    xdl_debug_fh.setLevel(logging.DEBUG)
    xdl_debug_fh.setFormatter(XDLFileFormatter())
    xdl_debug_fh.addFilter(console_filter)

def initialize_duration_xdl_file_handler(log_folder, exp_name):
    """Initialize handler for XDL duration level logs. Reason for using global
    variable is so that the handler doesn't get readded to the XDL logger with
    repeated calls to logger.addHandler.
    """
    global xdl_duration_fh
    xdl_duration_fh = logging.FileHandler(
        filename=os.path.join(log_folder, "{0}_step_durations.tsv".format(
            exp_name)), encoding='utf-8')
    xdl_duration_fh.setLevel(logging.INFO)
    xdl_duration_fh.setFormatter(logging.Formatter('%(message)s'))
    xdl_duration_fh.addFilter(duration_filter)

def initialize_info_pylabware_handler(log_folder, exp_name):
    """Initialize handler for PyLwabware Info level logs. Reason for using global
    variable is so that the handler doesn't get readded to the Pylabware logger
    with repeated calls to logger.addHandler.
    """
    global pylabware_info_fh
    pylabware_info_fh = logging.FileHandler(
        filename=os.path.join(log_folder, "{}_info.log".format(
            exp_name
        )), encoding='utf-8'
    )

    pylabware_info_fh.setLevel(logging.INFO)
    pylabware_info_fh.setFormatter(get_pylabware_file_formatter())
    pylabware_info_fh.addFilter(console_filter)

def initialize_debug_pylabware_handler(log_folder, exp_name):
    """Initialize handler for PyLwabware debug level logs. Reason for using global
    variable is so that the handler doesn't get readded to the Pylabware logger
    with repeated calls to logger.addHandler.
    """
    global pylabware_debug_fh
    pylabware_debug_fh = logging.FileHandler(
        filename=os.path.join(log_folder, "{}_debug.log".format(
            exp_name
        )), encoding='utf-8'
    )

    pylabware_debug_fh.setLevel(logging.DEBUG)
    pylabware_debug_fh.setFormatter(get_pylabware_file_formatter())
    pylabware_debug_fh.addFilter(console_filter)

def get_console_handler(logging_level):
    # create console handler which logs all messages
    ch = logging.StreamHandler()
    ch.setLevel(logging_level)

    # create formatter and add it to the handlers
    console_formatter = logging.Formatter(
        "%(asctime)s ; %(module)s ; %(message)s")
    ch.setFormatter(console_formatter)
    return ch

def get_info_file_handler(log_folder, exp_name):
    info_fh = logging.FileHandler(
        filename=os.path.join(log_folder, "{0}_info.log".format(
            exp_name)), encoding='utf-8')
    info_fh.setLevel(logging.INFO)
    info_fh.setFormatter(get_file_formatter())
    return info_fh

def get_debug_file_handler(log_folder, exp_name, level=logging.DEBUG):
    debug_fh = logging.FileHandler(
        filename=os.path.join(log_folder, "{0}_debug.log".format(
            exp_name)), encoding='utf-8')
    debug_fh.setLevel(level)
    debug_fh.setFormatter(get_file_formatter())
    return debug_fh
