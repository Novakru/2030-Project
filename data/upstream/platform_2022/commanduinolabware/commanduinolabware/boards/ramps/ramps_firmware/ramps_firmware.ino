/*
An example firmware to run Commanduino on Arduino board equipped with RAMPS shield
*/

//Pin mappings
#include "ramps.h"

// Command Handler and Manager for communication
#include <CommandHandler.h>
#include <CommandManager.h>

// Basic pin operations
#include <CommandDigitalRead.h>
#include <CommandDigitalWrite.h>
#include <CommandAnalogRead.h>
#include <CommandAnalogWrite.h>

// Stepper motors support
#include <AccelStepper.h>
#include <LinearAccelStepperActuator.h>
#include <CommandAccelStepper.h>
#include <CommandLinearAccelStepperActuator.h>

// CommandManager object for device registration
CommandManager cmdMgr;

// All stepper motor-based actuators
// X Motor itself
AccelStepper xMotor(AccelStepper::DRIVER, X_STEP_PIN, X_DIR_PIN);
//Plus EN/Home control
CommandLinearAccelStepperActuator X(xMotor, X_MIN_PIN, X_ENABLE_PIN);

AccelStepper yMotor(AccelStepper::DRIVER, Y_STEP_PIN, Y_DIR_PIN);
CommandLinearAccelStepperActuator Y(yMotor, Y_MIN_PIN, Y_ENABLE_PIN);

AccelStepper zMotor(AccelStepper::DRIVER, Z_STEP_PIN, Z_DIR_PIN);
CommandLinearAccelStepperActuator Z(zMotor, Z_MIN_PIN, Z_ENABLE_PIN);

// Extruder motors do not have limit switch pins on RAMPS
// Thus X_MAX is being used for E0
AccelStepper e0Motor(AccelStepper::DRIVER, E0_STEP_PIN, E0_DIR_PIN);
CommandLinearAccelStepperActuator E0(e0Motor, X_MAX_PIN, E0_ENABLE_PIN);

// And Y_MAX for E1
// Any other free pins can be used as well
AccelStepper e1Motor(AccelStepper::DRIVER, E1_STEP_PIN, E1_DIR_PIN);
CommandLinearAccelStepperActuator E1(e1Motor, Y_MAX_PIN, E1_ENABLE_PIN);

// Example PWM pin control
// to control output MOSFETs with PWM
CommandAnalogWrite Heater0(HEATER0_PIN);
CommandAnalogWrite Heater1(HEATER1_PIN);

// Built-in LED
CommandDigitalWrite LedWrite(LED_PIN);
// Example Digital pin read/write
CommandDigitalRead Servo1Read(SERVO1_PIN);
CommandDigitalWrite Servo1Write(SERVO1_PIN);
CommandDigitalRead Servo2Read(SERVO2_PIN);
CommandDigitalWrite Servo2Write(SERVO2_PIN);

// Example ADC pins read
CommandAnalogRead Temp0(TEMP0_PIN);
CommandAnalogRead Temp1(TEMP1_PIN);

void setup() {
    // Fire up the serial connection
    Serial.begin(115200);

    // Register all devices to the Manager
    X.registerToCommandManager(cmdMgr, "X");
    Y.registerToCommandManager(cmdMgr, "Y");
    Z.registerToCommandManager(cmdMgr, "Z");
    E0.registerToCommandManager(cmdMgr, "E0");
    E1.registerToCommandManager(cmdMgr, "E1");

    Heater0.registerToCommandManager(cmdMgr, "H0W");
    Heater1.registerToCommandManager(cmdMgr, "H1W");

    LedWrite.registerToCommandManager(cmdMgr, "LEDW");
    Servo1Read.registerToCommandManager(cmdMgr, "S1R");
    Servo1Write.registerToCommandManager(cmdMgr, "S1W");
    Servo2Read.registerToCommandManager(cmdMgr, "S2R");
    Servo2Write.registerToCommandManager(cmdMgr, "S2W");

    Temp0.registerToCommandManager(cmdMgr, "T0");
    Temp1.registerToCommandManager(cmdMgr, "T1");

    // Start the manager
    cmdMgr.init();
}

void loop() {
    // Update endlessly
    cmdMgr.update();
}
