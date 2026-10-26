"""Tools for controlling devices live from ChemIDE."""

from typing import Dict, Callable

def execute_start_stir(device, command_parameters):
    device.start_stirring()

def execute_stop_stir(device, command_parameters):
    device.stop_stirring()

def execute_set_stir_speed(device, command_parameters):
    device.set_speed(command_parameters['stir_speed'])

def execute_start_temperature_regulation(device, command_parameters):
    device.start_temperature_regulation()

def execute_stop_temperature_regulation(device, command_parameters):
    device.stop_temperature_regulation()

def execute_set_temperature(device, command_parameters):
    device.set_temperature(command_parameters['temperature'])

def execute_start_pressure_regulation(device, command_parameters):
    device.start_pressure_regulation()

def execute_stop_pressure_regulation(device, command_parameters):
    device.stop_pressure_regulation()

def execute_set_pressure(device, command_parameters):
    device.set_pressure(command_parameters['pressure'])

def execute_set_cooling_power(device, command_parameters):
    device.set_cooling_power(command_parameters['cooling_power'])

def execute_start_chill_petite_fleur(device, command_parameters):
    """Petite Fleur start chill is different as temperature ramp must be set
    here.
    """
    temp = command_parameters['temp']
    ramp = command_parameters['ramp']
    if ramp:
        device.ramp_temperature(temp, ramp)
    device.start_temperature_regulation()

def execute_pump(device, command_parameters):
    direction = command_parameters['direction']
    volume = command_parameters['volume']
    speed = command_parameters['speed']
    if direction == 'down':
        volume = -volume
    device.move_relative(volume, speed)

def execute_switch_valve(device, command_parameters):
    device.move_to_position(command_parameters['position'])

def execute_rotavap_lift_up(device, command_parameters):
    device.lift_up()

def execute_rotavap_lift_down(device, command_parameters):
    device.lift_down()


#: Dict of commands that ChemIDE can send and functions to execute those
#: commands no the appropriate device with the command parameters.
live_control_command_executors: Dict[str, Callable] = {
    # Stirring
    'start_stir': execute_start_stir,
    'stop_stir': execute_stop_stir,
    'set_stir_speed': execute_set_stir_speed,

    # Temperature control
    'start_temperature_regulation': execute_start_temperature_regulation,
    'stop_temperature_regulation': execute_stop_temperature_regulation,
    'set_temperature': execute_set_temperature,

    # Misc Chiller
    'set_cooling_power': execute_set_cooling_power,
    'start_chill_petite_fleur': execute_start_chill_petite_fleur,

    # Pump / Valve
    'pump': execute_pump,
    'switch_valve': execute_switch_valve,

    # Pressure control
    'start_pressure_regulation': execute_start_pressure_regulation,
    'stop_pressure_regulation': execute_stop_pressure_regulation,
    'set_pressure': execute_set_pressure,

    # Rotavap
    'rotavap_lift_up': execute_rotavap_lift_up,
    'rotavap_lift_down': execute_rotavap_lift_down,
}
