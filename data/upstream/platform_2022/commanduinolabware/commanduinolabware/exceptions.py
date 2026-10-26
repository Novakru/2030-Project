"""
.. module:: exceptions
    :platform: Unix, WIndows
    :synopsis: General exceptions for the CommanduinoLabware

.. moduleauthor:: Graham Keenan (Cronin Lab 2020)

"""
from commanduino.exceptions import CMError


class CMDeviceError(CMError):
    """ General catch-all class.
    """


class CMDeviceReplyError(CMDeviceError):
    """ Unexpected/wrong device reply
    """


class CMDeviceCommandError(CMDeviceError):
    """ Wrong parameters for device command
    """
