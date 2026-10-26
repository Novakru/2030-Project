"""Tools for background sensor reading."""

from typing import Dict, Callable
import random
import time


def simulation_sensor_read(device):
    """Provide placeholder sensor reading for testing purposes."""
    time.sleep(random.random())
    return random.random() * 100


#: Functions to use when taking sensor readings from devices
#: And the corresponding readings names
sensors_read_functions: Dict[str, Dict[str, Callable]] = {
    'ConductivitySensor': {
        'conductivity_combined': lambda device: device.take_reading_combined(),
    },
    'RCTDigitalHotplate': {
        'temperature': lambda device: device.get_temperature(),
    },
    'RETControlViscHotplate': {
        'temperature': lambda device: device.get_temperature(),
        'pH': lambda device: float(device.get_ph()),
    },
    'BME280Sensor': {
        'temperature': lambda device: device.get_temperature(),
        'pressure': lambda device: device.get_pressure(),
        'humidity': lambda device: device.get_humidity(),
    },
    'RGBSensor': {
        'red': lambda device: device.get_rgbc()['red'],
        'green': lambda device: device.get_rgbc()['green'],
        'blue': lambda device: device.get_rgbc()['blue'],
        'clear': lambda device: device.get_rgbc()['clear'],
    },
    'RTDSensor': {
        'temperature': lambda device: device.get_temperature(),
    },
    'BubbleSensor': {
        'bubbles': lambda device: device.take_reading(),
    },
}
