/*
An example firmware to run Commanduino on Arduino board equipped with SensorHub shield
*/

//Pin mappings
#include "sensorhub.h"

// Command Handler and Manager for communication
#include <CommandHandler.h>
#include <CommandManager.h>

// Basic pin operations
#include <CommandDigitalRead.h>
#include <CommandDigitalWrite.h>
#include <CommandAnalogRead.h>
#include <CommandAnalogWrite.h>

// I2C multiplexer
#include <CommandPCA9548A.h>

// Multiplexer address on the SensorHub
#define MUX_I2C_ADDR 0x70

// CommandManager object for device registration
CommandManager cmdMgr;

// MOSFETs with PWM control
CommandAnalogWrite CH1(MOSFET_CH1);
CommandAnalogWrite CH2(MOSFET_CH2);
CommandAnalogWrite CH3(MOSFET_CH3);
CommandAnalogWrite CH4(MOSFET_CH4);
CommandAnalogWrite CH5(MOSFET_CH5);
CommandAnalogWrite CH6(MOSFET_CH6);
CommandAnalogWrite CH7(MOSFET_CH7);
CommandAnalogWrite CH8(MOSFET_CH8);
CommandAnalogWrite CH9(MOSFET_CH9);
CommandAnalogWrite CH10(MOSFET_CH10);
CommandAnalogWrite CH11(MOSFET_CH11);
CommandAnalogWrite CH12(MOSFET_CH12);

// Analog sensors. Digital pin for each channel can be configured as
// either input or output, depending what one needs.
// Sensor 1
CommandAnalogRead S1AR(AIN1);
CommandDigitalRead S1DR(DIN1);
CommandDigitalWrite S1DW(DIN1);
/*
// Sensor 2
CommandAnalogRead S2AR(AIN2);
CommandDigitalRead S2DR(DIN2);
CommandDigitalWrite S2DW(DIN2);

// Sensor 3
CommandAnalogRead S3AR(AIN3);
CommandDigitalRead S3DR(DIN3);
CommandDigitalWrite S3DW(DIN3);
// Sensor 4
CommandAnalogRead S4AR(AIN4);
CommandDigitalRead S4DR(DIN4);
CommandDigitalWrite S4DW(DIN4);
// Sensor 5
CommandAnalogRead S5AR(AIN5);
CommandDigitalRead S5DR(DIN5);
CommandDigitalWrite S5DW(DIN5);
// Sensor 6
CommandAnalogRead S6AR(AIN6);
CommandDigitalRead S6DR(DIN6);
CommandDigitalWrite S6DW(DIN6);
// Sensor 7
CommandAnalogRead S7AR(AIN7);
CommandDigitalRead S7DR(DIN7);
CommandDigitalWrite S7DW(DIN7);
// Sensor 8
CommandAnalogRead S8AR(AIN8);
CommandDigitalRead S8DR(DIN8);
CommandDigitalWrite S8DW(DIN8);*/

// PCA9548A I2C multiplexer
CommandPCA9548A MUX(MUX_I2C_ADDR);


void setup() {
    // Fire up the serial connection
    Serial.begin(115200);

    // Register all devices to the Manager
    CH1.registerToCommandManager(cmdMgr, "CH1");
    CH2.registerToCommandManager(cmdMgr, "CH2");
    CH3.registerToCommandManager(cmdMgr, "CH3");
    CH4.registerToCommandManager(cmdMgr, "CH4");
    CH5.registerToCommandManager(cmdMgr, "CH5");
    CH6.registerToCommandManager(cmdMgr, "CH6");
    CH7.registerToCommandManager(cmdMgr, "CH7");
    CH8.registerToCommandManager(cmdMgr, "CH8");
    CH9.registerToCommandManager(cmdMgr, "CH9");
    CH10.registerToCommandManager(cmdMgr, "CH10");
    CH11.registerToCommandManager(cmdMgr, "CH11");
    CH12.registerToCommandManager(cmdMgr, "CH12");
    S1AR.registerToCommandManager(cmdMgr, "S1AR");
    S1DR.registerToCommandManager(cmdMgr, "S1DR");
    S1DW.registerToCommandManager(cmdMgr, "S1DW");
    /*S2AR.registerToCommandManager(cmdMgr, "S2AR");
    S2DR.registerToCommandManager(cmdMgr, "S2DR");
    S2DW.registerToCommandManager(cmdMgr, "S2DW");
    S3AR.registerToCommandManager(cmdMgr, "S3AR");
    S3DR.registerToCommandManager(cmdMgr, "S3DR");
    S3DW.registerToCommandManager(cmdMgr, "S3DW");
    S4AR.registerToCommandManager(cmdMgr, "S4AR");
    S4DR.registerToCommandManager(cmdMgr, "S4DR");
    S4DW.registerToCommandManager(cmdMgr, "S4DW");
    S5AR.registerToCommandManager(cmdMgr, "S5AR");
    S5DR.registerToCommandManager(cmdMgr, "S5DR");
    S5DW.registerToCommandManager(cmdMgr, "S5DW");
    S6AR.registerToCommandManager(cmdMgr, "S6AR");
    S6DR.registerToCommandManager(cmdMgr, "S6DR");
    S6DW.registerToCommandManager(cmdMgr, "S6DW");
    S7AR.registerToCommandManager(cmdMgr, "S7AR");
    S7DR.registerToCommandManager(cmdMgr, "S7DR");
    S7DW.registerToCommandManager(cmdMgr, "S7DW");
    S8AR.registerToCommandManager(cmdMgr, "S8AR");
    S8DR.registerToCommandManager(cmdMgr, "S8DR");
    S8DW.registerToCommandManager(cmdMgr, "S8DW");*/
    MUX.registerToCommandManager(cmdMgr, "MUX");
    // Start the manager
    cmdMgr.init();
}

void loop() {
    // Update endlessly
    cmdMgr.update();
}