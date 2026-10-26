import os
import shutil
import time
import appdirs
from termcolor import colored
from xdl import XDLController
from chemputerxdl import ChemputerPlatform
from chempiler import Chempiler
import ChemputerAPI

HERE = os.path.abspath(os.path.dirname(__file__))

def test_log(node, message):
    testing = colored('Testing', 'blue')
    node = colored(node, 'cyan', attrs=['bold'])
    print(f'{testing} {node}: {message}')

def pause(pause=2):
    time.sleep(pause)

def test_temperature_controller(xdlc, node_name):
    # Set temp
    test_log(node_name, 'Setting temperature to 30°C...')
    xdlc.c_temperature_controller_set_temp(
        temperature_controller=node_name, temp=30)
    pause()

    # Start
    test_log(node_name, 'Starting heating...')
    xdlc.c_temperature_controller_start(
        temperature_controller=node_name)
    pause()

    # Stop
    test_log(node_name, 'Stopping heating...')
    xdlc.c_temperature_controller_stop(
        temperature_controller=node_name)
    pause()

    # Get temp
    test_log(node_name, 'Getting temperature...')
    xdlc.c_temperature_controller_get_temp(
        temperature_controller=node_name,
        on_reading=lambda reading: test_log(
            node_name, f'Temperature reading is {reading}°C.')
    )
    pause()

    # Get temp setpoint
    test_log(node_name, 'Getting temperature setpoint...')
    xdlc.c_temperature_controller_get_temp_setpoint(
        temperature_controller=node_name,
        on_reading=lambda reading: test_log(
            node_name, f'Temperature setpoint reading is {reading}°C.')
    )
    pause()

def test_stirring_controller(xdlc, node_name):
    # Set speed
    test_log(node_name, 'Setting stirring to 250 RPM...')
    xdlc.c_stirring_controller_set_speed(
        stirring_controller=node_name, stir_speed=250)
    pause()

    # Start
    test_log(node_name, 'Starting stirring...')
    xdlc.c_stirring_controller_start(
        stirring_controller=node_name)
    pause()

    # Stop
    test_log(node_name, 'Stopping stirring...')
    xdlc.c_stirring_controller_stop(
        stirring_controller=node_name)
    pause()

    # Get speed
    test_log(node_name, 'Getting stirring...')
    xdlc.c_stirring_controller_get_speed(
        stirring_controller=node_name,
        on_reading=lambda reading: test_log(
            node_name, f'Stir speed reading is {reading}°C.')
    )
    pause()

    # Get speed setpoint
    test_log(node_name, 'Getting stirring setpoint...')
    xdlc.c_stirring_controller_get_speed_setpoint(
        stirring_controller=node_name,
        on_reading=lambda reading: test_log(
            node_name, f'Stir speed setpoint reading is {reading}°C.')
    )
    pause()

def test_pressure_controller(xdlc, node_name):
    # Set pressure
    test_log(node_name, 'Setting pressure to 300 RPM...')
    xdlc.c_pressure_controller_set_pressure(
        pressure_controller=node_name, pressure=300)
    pause()

    # Start
    test_log(node_name, 'Starting vacuum...')
    xdlc.c_pressure_controller_start(
        pressure_controller=node_name)
    pause()

    # Stop
    test_log(node_name, 'Stopping vacuum...')
    xdlc.c_pressure_controller_stop(
        pressure_controller=node_name)
    pause()

    # Get pressure
    test_log(node_name, 'Getting pressure...')
    xdlc.c_pressure_controller_get_pressure(
        pressure_controller=node_name,
        on_reading=lambda reading: test_log(
            node_name, f'Pressure reading is {reading}°C.')
    )
    pause()

    # Get pressure setpoint
    test_log(node_name, 'Getting pressure setpoint...')
    xdlc.c_pressure_controller_get_pressure_setpoint(
        pressure_controller=node_name,
        on_reading=lambda reading: test_log(
            node_name, f'Pressure setpoint reading is {reading}°C.')
    )
    pause()

    # Vent on
    test_log(node_name, 'Turning vent on...')
    xdlc.c_pressure_controller_vent_on(
        pressure_controller=node_name
    )
    pause()

    # Vent off
    test_log(node_name, 'Turning vent off...')
    xdlc.c_pressure_controller_vent_off(
        pressure_controller=node_name
    )
    pause()

def test_pump(xdlc, pump):
    """Move up then down pump max volume."""
    chempiler = xdlc.platform_controller
    graph = chempiler.graph.graph
    max_volume = graph.nodes[pump]['max_volume']

    test_log(pump, 'Aspiring max volume...')
    chempiler[pump].execute(('sink', 0), volume=max_volume, speed=50)
    chempiler[pump].wait_until_ready()

    test_log(pump, 'Dispensing max volume...')
    chempiler[pump].execute(('source', 0), volume=max_volume, speed=50)
    chempiler[pump].wait_until_ready()

def test_valve(xdlc, valve):
    """Switch valve to all ports."""
    chempiler = xdlc.platform_controller
    for i in range(6):
        test_log(valve, f'Switching to position {i}...')
        chempiler[valve].execute(('route', -1, i))
        chempiler[valve].wait_until_ready()

def test_conductivity_sensor(xdlc, conductivity_sensor):
    def on_reading(reading):
        test_log(
            conductivity_sensor, f'Received conductivity reading: {reading}')
    xdlc.read_conductivity_sensor(
        sensor=conductivity_sensor, on_reading=on_reading)

def test_pneumatic_controller(xdlc, pneumatic_controller):
    for i in range(1, 7):
        test_log(
            pneumatic_controller,
            'Switching channel {i} to high pressure argon'
        )
        xdlc.c_switch_argon(
            pneumatic_controller=pneumatic_controller, port=i, pressure='high')
        pause()

        test_log(pneumatic_controller, 'Switching channel {i} to vacuum')
        xdlc.c_switch_vacuum(
            pneumatic_controller=pneumatic_controller, port=i)
        pause()

        test_log(
            pneumatic_controller, 'Switching channel {i} to low pressure argon')
        xdlc.c_switch_argon(
            pneumatic_controller=pneumatic_controller, port=i, pressure='low')
        pause()


TEST_FNS = {
    'ChemputerPump': test_pump,
    'ChemputerValve': test_valve,
    'Microstar75Stirrer': test_stirring_controller,
    'HeiTorque100PrecisionStirrer': test_stirring_controller,
    'RCTDigitalHotplate': [
        test_temperature_controller,
        test_stirring_controller
    ],
    'RETControlViscHotplate': [
        test_temperature_controller,
        test_stirring_controller,
    ],
    'ConductivitySensor': test_conductivity_sensor,
    'RV10Rotovap': [
        test_stirring_controller,
        test_temperature_controller,
    ],
    'R300Rotovap': [
        test_temperature_controller,
        test_stirring_controller,
        test_pressure_controller,
    ],
    'CF41Chiller': test_temperature_controller,
    'PetiteFleurChiller': test_temperature_controller,
    'CVC3000VacuumPump': test_pressure_controller,
    'PneumaticController': test_pneumatic_controller,
}

def get_xdl_controller(graph_file, simulation=False):
    c = get_chempiler(graph_file, simulation=simulation)
    xdlc = XDLController(ChemputerPlatform, c, graph_file)
    return xdlc

def get_chempiler(graph_file, simulation=False):
    output_dir = os.path.join(HERE, 'chempiler_output')
    if os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
    return Chempiler(
        graph_file=graph_file,
        simulation=simulation,
        experiment_code='live-test',
        device_modules=[ChemputerAPI],
        output_dir=appdirs.user_data_dir('chemputer'),
    )

def test_node(chempiler, node, node_class):
    """Test individual node."""

    # Node should be tested
    if node_class in TEST_FNS:

        # Get test functions
        test_fns = TEST_FNS[node_class]
        if type(test_fns) != list:
            test_fns = [test_fns]

        # Run tests
        for test_fn in test_fns:
            test_fn(chempiler, node)

        # Line break for neatness of output
        print('')

def run_tests(graph_file, target_node=None, simulation=False):
    """Test every node in graph."""

    # Instantiate Chempiler and get graph object
    xdlc = get_xdl_controller(graph_file, simulation=simulation)
    graph = xdlc.platform_controller.graph.graph

    # Check target node in graph
    if target_node is not None:
        if target_node not in list(graph.nodes()):
            print(f'Target node {target_node} not in graph.')
            return

    # Test every node in graph
    for node, data in graph.nodes(data=True):
        if target_node is None or target_node == node:
            test_node(xdlc, node, data['class'])

def test_vent_vacuum(graph_file, pressure_controller, simulation=False):
    xdlc = get_xdl_controller(graph_file, simulation=simulation)
    test_log(pressure_controller, 'Setting pressure to 400 mbar...')
    xdlc.c_pressure_controller_set_pressure(
        pressure_controller=pressure_controller,
        pressure=400
    )
    test_log(pressure_controller, 'Starting vacuum...')
    xdlc.c_pressure_controller_start(pressure_controller=pressure_controller)
    time.sleep(10)
    test_log(pressure_controller, 'Stopping vacuum...')
    xdlc.c_pressure_controller_stop(pressure_controller=pressure_controller)
    test_log(pressure_controller, 'Venting vacuum...')
    xdlc.vent_vacuum(vessel=None, pressure_controller=pressure_controller)

def test_wait_for_temp(graph_file, vessel, simulation=False):
    xdlc = get_xdl_controller(graph_file, simulation=simulation)

    test_log(vessel, 'Starting heating to 27°C...')
    xdlc.start_heat_chill(vessel=vessel, temp=27)

    test_log(vessel, 'Waiting to reach 27°C...')
    xdlc.wait_for_temp(vessel=vessel)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('graph', type=str)
    parser.add_argument('--node', type=str)
    parser.add_argument('--simulation', action='store_true')
    parser.add_argument('--vent', type=str)
    parser.add_argument('--wait_for_temp', type=str)
    args = parser.parse_args()

    if not args.graph:
        print('Give a path to the graph file of the rig to test.')
        return

    # Test VentVacuum
    if args.vent:
        test_vent_vacuum(args.graph, args.vent, simulation=args.simulation)
        return

    # Test WaitForTemp
    elif args.wait_for_temp:
        test_wait_for_temp(
            args.graph, args.wait_for_temp, simulation=args.simulation)
        return

    elif args.node:
        run_tests(args.graph, args.node, simulation=args.simulation)
        return

    # Test base steps for node in graph
    run_tests(args.graph, simulation=args.simulation)


if __name__ == '__main__':
    main()
