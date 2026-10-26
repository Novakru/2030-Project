"""SerialLabware2  exceptions"""


class SLConnectionError(ConnectionError):
    """ Generic connection error, base class."""


class SLConnectionProtocolError(SLConnectionError):
    """Error in transport protocol."""


class SLConnectionTimeoutError(SLConnectionError):
    """Connection timeout error."""


class SLDeviceError(Exception):
    """Generic device error, base class."""


class SLDeviceCommandError(SLDeviceError):
    """Error in processing device command.

    This should be any error arising BEFORE the command has been sent to a device.
    """


class SLDeviceReplyError(SLDeviceError):
    """Error in processing device reply.

    This should be any error arising AFTER the command has been sent to the device.
    """


class SLDeviceInternalError(SLDeviceReplyError):
    """Error returned by device as a response to command.
    """
