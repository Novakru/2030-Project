"""
Module contains utility functions used for controlling various sensors via
ChemputerAPI.
"""

from functools import wraps


def check_channel(f):
    """ Decorator to check if the channel was set, e.g. using i2c switch. """
    @wraps(f)
    def wrapper(*args, **kwargs):
        instance = args[0]
        logger = instance.device.logger

        if instance.channel is not None:
            # acquiring i2c switch lock
            instance.device.i2c_mux_lock.acquire()
            logger.debug('I2C switch lock acquired by %s', instance.name)
            # switching i2c channel
            instance.device.i2c_mux_channels_on(instance.channel)

        # recording result
        result = f(*args, **kwargs)

        if instance.channel is not None:
            # switching i2c channel back
            instance.device.i2c_mux_channels_off(instance.channel)
            # releasing i2c switch lock
            instance.device.i2c_mux_lock.release()
            logger.debug('I2C switch lock released by %s', instance.name)

        # returning result
        return result
    return wrapper
