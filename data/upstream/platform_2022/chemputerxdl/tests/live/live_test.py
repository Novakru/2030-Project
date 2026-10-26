import sys
import appdirs
import os
import shutil
import time
from termcolor import colored

from chempiler import Chempiler
import ChemputerAPI

HERE = os.path.abspath(os.path.dirname(__file__))

pause = 2

def test_log(node, message):
    testing = colored('Testing', 'blue')
    node = colored(node, 'cyan', attrs=['bold'])
    print(f'{testing} {node}: {message}')

def test_pump(chempiler, pump):
    """Move up then down pump max volume."""
    graph = chempiler.graph.graph
    max_volume = graph.nodes[pump]['max_volume']

    test_log(pump, 'Aspiring max volume...')
    chempiler[pump].execute(('sink', 0), volume=max_volume, speed=50)
    chempiler[pump].wait_until_ready()

    test_log(pump, 'Dispensing max volume...')
    chempiler[pump].execute(('source', 0), volume=max_volume, speed=50)
    chempiler[pump].wait_until_ready()

def test_valve(chempiler, valve):
    """Switch valve to all ports."""
    for i in range(6):
        test_log(valve, f'Switching to position {i}...')
        chempiler[valve].execute(('route', -1, i))
        chempiler[valve].wait_until_ready()

def test_stirrer(chempiler, stirrer):
    """Set stir rate and start and stop stirrer."""
    test_log(stirrer, 'Setting stir rate to 200 RPM...')
    chempiler[stirrer].stir_rate_sp = 200
    time.sleep(pause)

    test_log(stirrer, 'Starting stirrer...')
    chempiler[stirrer].start_stirrer()
    time.sleep(pause)

    test_log(stirrer, 'Setting stir rate to 400 RPM...')
    chempiler[stirrer].stir_rate_sp = 400
    time.sleep(pause)

    test_log(stirrer, 'Stopping stirrer...')
    chempiler[stirrer].stop_stirrer()
    time.sleep(pause)

def test_hotplate(chempiler, hotplate):
    """Set stir rate and start and stop stirring, then set temp and start and
    stop heating.
    """
    test_stirrer(chempiler, hotplate)

    test_log(hotplate, 'Setting hotplate temp to 50°C...')
    chempiler[hotplate].temperature_sp = 50
    time.sleep(pause)

    test_log(hotplate, 'Starting heating...')
    chempiler[hotplate].start_heater()
    time.sleep(pause)

    test_log(hotplate, 'Setting hotplate temp to 25°C...')
    chempiler[hotplate].temperature_sp = 25
    time.sleep(pause)

    test_log(hotplate, 'Stopping heating...')
    chempiler[hotplate].stop_heater()
    time.sleep(pause)

def test_conductivity_sensor(chempiler, conductivity_sensor):
    """Take conductivity reading."""
    test_log(conductivity_sensor, 'Taking conductivity sensor reading...')
    reading = chempiler[conductivity_sensor].conductivity
    test_log(conductivity_sensor, f'Conductivity reading is {reading}.')
    time.sleep(pause)

def test_rotavap(chempiler, rotavap):
    """Lift arm down, start rotation, set rotation speed, stop rotation,
    start heating, set temperature, stop heating, lift arm up.
    """
    test_log(rotavap, 'Lifting arm down...')
    chempiler[rotavap].lift_down()

    test_log(rotavap, 'Setting rotation speed to 150 RPM...')
    chempiler[rotavap].rotation_speed_sp = 150
    time.sleep(pause)

    test_log(rotavap, 'Start rotating flask...')
    chempiler[rotavap].start_rotation()
    time.sleep(pause)

    test_log(rotavap, 'Stop rotating flask...')
    chempiler[rotavap].stop_rotation()
    time.sleep(pause)

    test_log(rotavap, 'Setting temperature to 50°C...')
    chempiler[rotavap].temperature_sp = 50
    time.sleep(pause)

    test_log(rotavap, 'Starting heating...')
    chempiler[rotavap].start_heater()
    time.sleep(pause)

    test_log(rotavap, 'Stopping heating...')
    chempiler[rotavap].stop_heater()
    time.sleep(pause)

    test_log(rotavap, 'Lifting arm up...')
    chempiler[rotavap].lift_up()

def test_chiller(chempiler, chiller):
    """Set temperature, start chiller, stop chiller."""

    test_log(chiller, 'Setting chiller temperature to 0°C...')
    chempiler[chiller].set_temperature(temp=0)
    time.sleep(pause)

    test_log(chiller, 'Starting chiller...')
    chempiler[chiller].start()
    time.sleep(pause)

    test_log(chiller, 'Stopping chiller...')
    chempiler[chiller].stop()
    time.sleep(pause)

def test_vacuum(chempiler, vacuum):
    """Set vacuum pressure, start vacuum, stop vacuum, vent vacuum."""

    test_log(vacuum, 'Setting vacuum pressure to 400 mbar...')
    chempiler[vacuum].vacuum_sp = 400
    time.sleep(pause)

    test_log(vacuum, 'Starting vacuum...')
    chempiler[vacuum].start()
    time.sleep(pause)

    test_log(vacuum, 'Stopping vacuum...')
    chempiler[vacuum].stop()
    time.sleep(pause)

    test_log(vacuum, 'Venting vacuum...')
    chempiler[vacuum].vent()
    time.sleep(pause)

def test_pneumatic_controller(chempiler, pneumatic_controller):
    """Switch to low pressure argon, high pressure argon and vacuum."""

    test_log(pneumatic_controller, 'Switching channel 1 to vacuum...')
    chempiler[pneumatic_controller].switch_vacuum(channel=1)
    time.sleep(pause)

    test_log(
        pneumatic_controller,
        'Switching channel 1 to high pressure inert gas...'
    )
    chempiler[pneumatic_controller].switch_argon(channel=1, pressure='high')
    time.sleep(pause)

    test_log(
        pneumatic_controller,
        'Switching channel 1 to low pressure inert gas...'
    )
    chempiler[pneumatic_controller].switch_argon(channel=1, pressure='low')
    time.sleep(pause)


TEST_FNS = {
    'ChemputerPump': test_pump,
    'ChemputerValve': test_valve,
    'Microstar75Stirrer': test_stirrer,
    'HeiTorque100PrecisionStirrer': test_stirrer,
    'RCTDigitalHotplate': test_hotplate,
    'RETControlViscHotplate': test_hotplate,
    'ConductivitySensor': test_conductivity_sensor,
    'RV10Rotovap': test_rotavap,
    'CF41Chiller': test_chiller,
    'PetiteFleurChiller': test_chiller,
    'CVC3000VacuumPump': test_vacuum,
    'PneumaticController': test_pneumatic_controller,
}

def get_chempiler(graph_file):
    output_dir = os.path.join(HERE, 'chempiler_output')
    if os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
    return Chempiler(
        graph_file=graph_file,
        simulation=False,
        experiment_code='live-test',
        device_modules=[ChemputerAPI],
        output_dir=appdirs.user_data_dir('chemputer'),
    )

def test_node(chempiler, node, node_class):
    """Test individual node."""

    # Node should be tested
    if node_class in TEST_FNS:

        # Get test function
        test_fn = TEST_FNS[node_class]

        # Run test
        test_fn(chempiler, node)

        # Line break for neatness of output
        print('')

def run_tests(graph_file):
    """Test every node in graph."""

    # Instantiate Chempiler and get graph object
    chempiler = get_chempiler(graph_file)
    graph = chempiler.graph.graph

    # Test every node in graph
    for node, data in graph.nodes(data=True):
        test_node(chempiler, node, data['class'])

def main():
    if len(sys.argv) != 2:
        print('Give a path to the graph file of the rig to test.')
        return

    graph_file = sys.argv[1]
    run_tests(graph_file)


if __name__ == '__main__':
    main()
