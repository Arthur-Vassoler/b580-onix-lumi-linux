/*---------------------------------------------------------*\
| OnixArcController.h                                       |
|                                                           |
|   Driver for ONIX LUMI Intel Arc graphics cards           |
|                                                           |
|   This file is part of the OpenRGB project                |
|   SPDX-License-Identifier: GPL-2.0-or-later               |
\*---------------------------------------------------------*/

#pragma once

#include <string>
#include "i2c_smbus.h"

/*---------------------------------------------------------*\
| The lighting controller lives behind the card's AMC        |
| (Add-in card Management Controller) on the GPU's internal  |
| I2C bus, at address 0x28.  The protocol is a stream of     |
| (register, value) pairs written in a single I2C            |
| transaction, followed by a one byte read which echoes the  |
| last value written.                                        |
\*---------------------------------------------------------*/
#define ONIX_ARC_I2C_ADDRESS        0x28

enum
{
    ONIX_REG_BYPASS                 = 0x0F,
    ONIX_REG_MODE                   = 0x10,
    ONIX_REG_RUNWAY_RESPONSE        = 0x11,
    ONIX_REG_RUNWAY_INTERVAL        = 0x12,
    ONIX_REG_ONECOLOR_RESPONSE      = 0x13,
    ONIX_REG_DIRECTION              = 0x14,
    ONIX_REG_SERIAL_RESPONSE        = 0x16,
    ONIX_REG_SERIAL_SPEED           = 0x17,
    ONIX_REG_RAINBOW_RESPONSE       = 0x18,
    ONIX_REG_RAINBOW_SPEED          = 0x19,
    ONIX_REG_CUSTOM_RED             = 0x1A,
    ONIX_REG_CUSTOM_GREEN           = 0x1B,
    ONIX_REG_CUSTOM_BLUE            = 0x1C,
    ONIX_REG_STACKING_SPEED         = 0x20,
    ONIX_REG_STRIP_LENGTH           = 0x27,   /* LED count; the card has 14 */
    ONIX_REG_RUNWAY_CHASER          = 0x29,
    ONIX_REG_BRIGHTNESS             = 0x3E,
    ONIX_REG_BREATHING_TEMPO        = 0xC8,
    ONIX_REG_BREATHING_RED          = 0xC9,
    ONIX_REG_BREATHING_GREEN        = 0xCA,
    ONIX_REG_BREATHING_BLUE         = 0xCB,
};

enum
{
    ONIX_MODE_RAINBOW               = 0x00,
    ONIX_MODE_CUSTOM                = 0x01,
    ONIX_MODE_BREATHING             = 0x02,
    ONIX_MODE_SERIAL                = 0x03,
    ONIX_MODE_RUNWAY                = 0x04,
    ONIX_MODE_ONECOLOR              = 0x05,
    ONIX_MODE_BLOCK_STACKING        = 0x06,
};

/*---------------------------------------------------------*\
| Value written to the brightness register by the vendor     |
| tool when lighting is enabled.  Brightness zero is off;     |
| there is no separate enable register.                      |
\*---------------------------------------------------------*/
#define ONIX_BRIGHTNESS_DEFAULT     0x88

/*---------------------------------------------------------*\
| Number of LEDs on the strip, which register 0x27 declares   |
| to the firmware.  The vendor tool writes it once at         |
| startup; effects run over however many LEDs it says, so a   |
| stale value makes them cover only part of the strip.        |
\*---------------------------------------------------------*/
#define ONIX_STRIP_LENGTH           0x0E

class OnixArcController
{
public:
    OnixArcController(i2c_smbus_interface* bus,
                      unsigned char address,
                      const std::string& name);
    ~OnixArcController();

    std::string     GetDeviceName();
    std::string     GetDeviceLocation();

    /*-----------------------------------------------------*\
    | Declares the strip length to the firmware.  Idempotent |
    | and invisible: it does not change what is lit, it only |
    | tells the card how many LEDs the effects span.         |
    |                                                        |
    | The vendor tool also writes brightness and the bypass  |
    | flag at startup, from its own configuration file.  We  |
    | write neither: brightness would override whatever the  |
    | user last set, and bypass hands the strip over to the  |
    | motherboard's ARGB header, which is a user preference   |
    | this driver has no business flipping on detection.     |
    \*-----------------------------------------------------*/
    void            Initialize();

    void            SetMode(unsigned char mode);
    void            SetBrightness(unsigned char brightness);
    void            SetCustomColor(unsigned char r, unsigned char g, unsigned char b);
    void            SetBreathingColor(unsigned char r, unsigned char g, unsigned char b);
    void            SetRegister(unsigned char reg, unsigned char value);

private:
    i2c_smbus_interface*    bus;
    unsigned char           dev;
    std::string             name;

    /*-----------------------------------------------------*\
    | Writes one transaction of (register, value) pairs and  |
    | then waits.  Never batch a mode change together with   |
    | other registers: the card accepts the transaction but  |
    | the lighting goes dark.  The vendor tool issues one     |
    | logical command per transaction and so do we.          |
    \*-----------------------------------------------------*/
    void            WritePairs(const unsigned char* pairs, unsigned int length);
};
