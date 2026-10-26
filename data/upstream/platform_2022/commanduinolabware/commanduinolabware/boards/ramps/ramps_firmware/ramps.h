/**
RAMPS pin mappings
These provide mappings between pin functions on RAMPS and physical pins on Arduino Mega
**/

// X motor on the RAMPS, marked X on the shield
#define X_STEP_PIN         54
#define X_DIR_PIN          55
#define X_ENABLE_PIN       38

// Y motor on te RAMPS, marked Y on the shield
#define Y_STEP_PIN         60
#define Y_DIR_PIN          61
#define Y_ENABLE_PIN       56

// Z motor on the RAMPS, marked Z on the shield
#define Z_STEP_PIN         46
#define Z_DIR_PIN          48
#define Z_ENABLE_PIN       62

// E0 motor on the RAMPS, marked E0 on the shield (Top two slots)
#define E0_STEP_PIN         26
#define E0_DIR_PIN          28
#define E0_ENABLE_PIN       24

// E1 motor on the RAMPS, marked E1 on the shield (Top two slots)
#define E1_STEP_PIN         36
#define E1_DIR_PIN          34
#define E1_ENABLE_PIN       30

//Motor endstops
#define X_MIN_PIN            3
#define X_MAX_PIN            2

#define Y_MIN_PIN           14
#define Y_MAX_PIN           15

#define Z_MIN_PIN           18
#define Z_MAX_PIN           19

// MOSFET outputs
#define HEATED_BED_PIN       8
#define HEATER0_PIN          9
#define HEATER1_PIN         10

// Servo connectors
#define SERVO1_PIN          11
#define SERVO2_PIN           6
#define SERVO3_PIN           5
#define SERVO4_PIN           4

// Thermistor connectors - ADC inputs
#define TEMP0_PIN           13   // ANALOG NUMBERING
#define TEMP1_PIN           14   // ANALOG NUMBERING
#define TEMP2_PIN           15   // ANALOG NUMBERING

#define LED_PIN             13