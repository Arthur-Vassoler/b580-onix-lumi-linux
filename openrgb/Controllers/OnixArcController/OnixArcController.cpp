/*---------------------------------------------------------*\
| OnixArcController.cpp                                     |
|                                                           |
|   Driver for ONIX LUMI Intel Arc graphics cards           |
|                                                           |
|   This file is part of the OpenRGB project                |
|   SPDX-License-Identifier: GPL-2.0-or-later               |
\*---------------------------------------------------------*/

#include <cstdio>
#include <chrono>
#include <thread>
#include "OnixArcController.h"

/*---------------------------------------------------------*\
| Pause between transactions.  Measured: 50 ms is enough for |
| a mode change to settle before the following registers are |
| written.  Without the gap the card goes dark.              |
\*---------------------------------------------------------*/
#define ONIX_TRANSACTION_DELAY_MS   50

OnixArcController::OnixArcController(i2c_smbus_interface* bus, unsigned char address, const std::string& name)
{
    this->bus   = bus;
    this->dev   = address;
    this->name  = name;
}

OnixArcController::~OnixArcController()
{
}

std::string OnixArcController::GetDeviceName()
{
    return(name);
}

std::string OnixArcController::GetDeviceLocation()
{
    char address[8];

    snprintf(address, sizeof(address), "0x%02X", dev);

    return("I2C: " + std::string(bus->info.device_name) + ", address " + address);
}

void OnixArcController::WritePairs(const unsigned char* pairs, unsigned int length)
{
    unsigned char buffer[16];

    if(length > sizeof(buffer))
    {
        return;
    }

    for(unsigned int i = 0; i < length; i++)
    {
        buffer[i] = pairs[i];
    }

    bus->i2c_write_block(dev, length, buffer);

    /*-----------------------------------------------------*\
    | The card returns one byte echoing the last value       |
    | written.  The vendor tool reads it and discards it;    |
    | we skip the read entirely, which the hardware accepts. |
    \*-----------------------------------------------------*/
    std::this_thread::sleep_for(std::chrono::milliseconds(ONIX_TRANSACTION_DELAY_MS));
}

void OnixArcController::SetMode(unsigned char mode)
{
    unsigned char pairs[2] = { ONIX_REG_MODE, mode };

    WritePairs(pairs, 2);
}

void OnixArcController::SetBrightness(unsigned char brightness)
{
    unsigned char pairs[2] = { ONIX_REG_BRIGHTNESS, brightness };

    WritePairs(pairs, 2);
}

void OnixArcController::SetDirection(unsigned char direction)
{
    unsigned char pairs[2] = { ONIX_REG_DIRECTION, direction };

    WritePairs(pairs, 2);
}

void OnixArcController::SetCustomColor(unsigned char red, unsigned char green, unsigned char blue)
{
    unsigned char pairs[6] =
    {
        ONIX_REG_CUSTOM_RED,    red,
        ONIX_REG_CUSTOM_GREEN,  green,
        ONIX_REG_CUSTOM_BLUE,   blue
    };

    WritePairs(pairs, 6);
}

void OnixArcController::SetBreathingColor(unsigned char red, unsigned char green, unsigned char blue)
{
    unsigned char pairs[6] =
    {
        ONIX_REG_BREATHING_RED,     red,
        ONIX_REG_BREATHING_GREEN,   green,
        ONIX_REG_BREATHING_BLUE,    blue
    };

    WritePairs(pairs, 6);
}

void OnixArcController::SetRegister(unsigned char reg, unsigned char value)
{
    unsigned char pairs[2] = { reg, value };

    WritePairs(pairs, 2);
}
