# Commanduino Labware

This package is a pre-built, Commanduino-ready Arduino device that has most of the common functionality required to interface with stepper motor and pin read/writes.

## Requirements

Read the documentation of [Commanduino](https://github.com/croningp/commanduino).

This will guide you through the installation process and how to install the required Arduino libraries to flash your boards.


## Installation

* Clone the repository
```
git clone http://datelore.chem.gla.ac.uk/Chemputer/commanduinolabware.git --branch develop
```

* Install the Requirements.txt
  * This will install the [Commanduino](https://github.com/croningp/commanduino) library and the ```pyserial``` library
```
pip install -r requirements.txt
```

* Run the setup script for the package
```
python setup.py install --user
```

* The package should now be installed and can be imported into a python script:
```python
from commanduinolabware import CommanduinoLabwareDevice
```

## Usage


```python
from commanduinolabware import CommanduinoLabwareDevice

# Two different ways of instantiating a device

# 1.) Defining ports and using a default configuration from the Chemputer Graph Maker
device = CommanduinoLabwareDevice("COM5", "COM6")

# 2.) Defining ports and a custom devices dictionary from the Chemputer Graph Maker (NYI)
device = CommanduinoLabwareDevice("COM5", "COM6", devices={...})

# 3.) Supplying a path to a configuration file which is read and and instantiated from that
device = CommanduinoLabwareDevice(configfile="path/to/config.json")

# Call device methods dependent on registered devices
device.set_pin_pwm("pin5", 125)
device.home_motor("msd1")

# etc. etc.
```

* Each CommanduinoLabware device requires a configuration file that details serial ports and devices registered to the Arduino.
* When using the Chemputer Graph app, this configuration is constructed from the detailed supplied in the graph.
  * Configuration file is not needed in this case.

### Example Configuration File

```json
{
    "ios": [
        {
            "type": "serial"
            "port": "/dev/ttyACM0"
        },
        {
            "type": "serial"
            "port": "COM5"
        },
        {
            "type": "tcpip"
            "port": "192.168.1.55"
        }
    ],
    "devices": {
        "wheel": {
            "command_id": "X",
            "config": {
                "reverted_direction": false,
                "enabled_acceleration": false,
                "speed": 5000
            }
        },
        "motor_2": {
            "command_id": "Y",
            "config": {
                "reverted_direction": false,
                "enabled_acceleration": false,
                "speed": 8000
            }
        },
        "motor_3": {
            "command_id": "Z",
            "config": {
                "reverted_direction": false,
                "enabled_acceleration": false,
                "speed": 2000
            }
        },
        "motor_4": {
            "command_id": "E0",
            "config": {
                "reverted_direction": false,
                "enabled_acceleration": true,
                "speed": 8000,
                "acceleration": 3000
            }
        },
        "motor_5": {
            "command_id": "E1",
            "config": {
                "reverted_direction": true,
                "enabled_acceleration": false,
                "reverted_switch": true,
                "speed": 12000,
                "homing_speed": 5000
            }
        },
        "A1R": {
            "command_id": "a1r"
        },
        "A1W": {
            "command_id": "a1w"
        },
        "D1R": {
            "command_id": "d1r"
        },
        "D1W": {
            "command_id": "d1w"
        }
    }
}
```

* ```ios```
  * These are the serial/TCP-IP ports which are connected to the Arduino
  * Configuration can contain device information for multiple Arduino boards, so long as the ports for each board are defined here
  * The ports also act as a fall back, meaning that it will check each defined port until it finds a connected device.
* ```devices```
  * Dictionary of devices containing information relevant to each device
  * Each device name is what Commanduino uses for identifying the correct underlying object
  * Can contain devices for multiple Arduino boards, so long as the ports for each Arduino are defined (see above).
  * Each device requires a ```command_id```, this is the ID that is supplied in the Arduino firmware so Commanduino knows which device to talk to
  * Stepper motors have a seperate ```config``` entry in their device information.
  * This is to default certain attributes of the motor such as speed, direction, etc (See [Commanduino](https://github.com/croningp/commanduino) documentation for more information)

### Example Firmware
Example firmware code for the Arduino. This defines 5 motors that can be used with a RAMPS shield and defines analog/digital read/write pins. Change as necessary.
```cpp
/**
PIN ALLOCATIONS ON ARDUINO RAMPS SHIELD

#define X_STEP_PIN         54
#define X_DIR_PIN          55
#define X_ENABLE_PIN       38

#define Y_STEP_PIN         60
#define Y_DIR_PIN          61
#define Y_ENABLE_PIN       56

#define Z_STEP_PIN         46
#define Z_DIR_PIN          48
#define Z_ENABLE_PIN       62

#define E0_STEP_PIN         26
#define E0_DIR_PIN          28
#define E0_ENABLE_PIN       24

#define E1_STEP_PIN         36
#define E1_DIR_PIN          34
#define E1_ENABLE_PIN       30

#define X_MIN_PIN          3
#define X_MAX_PIN          2
#define Y_MIN_PIN          14
#define Y_MAX_PIN          15
#define Z_MIN_PIN          18
#define Z_MAX_PIN          19
**/

/* Command Handler and Manager for communication */
#include <CommandHandler.h>
#include <CommandManager.h>

// CommandManager object for device registration
CommandManager cmdMgr;

/* Needed for the Stepper Motors */
#include <AccelStepper.h>
#include <LinearAccelStepperActuator.h>

/* Command Varieties needed for Commanduino */
#include <CommandAccelStepper.h>
#include <CommandLinearAccelStepperActuator.h>


// Pin operations
#include <CommandDigitalRead.h>
#include <CommandDigitalWrite.h>
#include <CommandAnalogRead.h>
#include <CommandAnalogWrite.h>

// X motor on the RAMPS, marked X on the shield
AccelStepper xMotor(AccelStepper::DRIVER, 54, 55);
CommandLinearAccelStepperActuator X(xMotor, 3, 38);

// Y motor on te RAMPS, marked Y on the shield
AccelStepper yMotor(AccelStepper::DRIVER, 60, 61);
CommandLinearAccelStepperActuator Y(yMotor, 14, 56);

// Z motor on the RAMPS, marked Z on the shield
AccelStepper zMotor(AccelStepper::DRIVER, 46, 48);
CommandLinearAccelStepperActuator Z(zMotor, 18, 62);

// E0 motor on the RAMPS, marked E0 on the shield (Top two slots)
AccelStepper e0Motor(AccelStepper::DRIVER, 26, 28);
CommandLinearAccelStepperActuator E0(e0Motor, 2, 24);

// E1 motor on the RAMPS, marked E1 on the shield (Top two slots)
AccelStepper e1Motor(AccelStepper::DRIVER, 36, 34);
CommandLinearAccelStepperActuator E1(e1Motor, 15, 30);

// Example Analog pin read/write
CommandAnalogRead a1Read(8);
CommandAnalogWrite a1Write(8);
CommandAnalogRead a2Read(9);
CommandAnalogWrite a2Write(9);

// Example Digitial pin read/write
CommandDigitalRead d1Read(20);
CommandDigitalWrite d1Write(20);
CommandDigitalRead d2Read(21);
CommandDigitalWrite d2Write(21);

void setup() {
    // Fire up the serial connection
    Serial.begin(115200);

    // Register all devices to the Manager
    X.registerToCommandManager(cmdMgr, "X");
    Y.registerToCommandManager(cmdMgr, "Y");
    Z.registerToCommandManager(cmdMgr, "Z");
    E0.registerToCommandManager(cmdMgr, "E0");
    E1.registerToCommandManager(cmdMgr, "E1");

    a1Read.registerToCommandManager(cmdMgr, "a1r");
    a1Write.registerToCommandManager(cmdMgr, "a1w");
    a2Read.registerToCommandManager(cmdMgr, "a2r");
    a2Write.registerToCommandManager(cmdMgr, "a2w");

    d1Read.registerToCommandManager(cmdMgr, "d1r");
    d1Write.registerToCommandManager(cmdMgr, "d1w");
    d2Read.registerToCommandManager(cmdMgr, "d2r");
    d2Write.registerToCommandManager(cmdMgr, "d2w");

    // Start the manager
    cmdMgr.init();
}

void loop() {
    // Update endlessly
    cmdMgr.update();
}
```