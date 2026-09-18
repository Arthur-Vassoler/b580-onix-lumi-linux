/*---------------------------------------------------------*\
| OnixArcControllerDetect.cpp                               |
|                                                           |
|   Detector for ONIX LUMI Intel Arc graphics cards         |
|                                                           |
|   This file is part of the OpenRGB project                |
|   SPDX-License-Identifier: GPL-2.0-or-later               |
\*---------------------------------------------------------*/

#include "DetectionManager.h"
#include "i2c_smbus.h"
#include "LogManager.h"
#include "OnixArcController.h"
#include "pci_ids.h"
#include "RGBController.h"
#include "RGBController_OnixArc.h"

#define DETECTOR_NAME   "ONIX LUMI Intel Arc"

/*---------------------------------------------------------*\
| The lighting controller shares its I2C address with the    |
| card's AMC, which the graphics driver also talks to.  A    |
| one byte read is the gentlest probe the device accepts:    |
| it returns the last value written and has no side effect.  |
|                                                            |
| Do not probe with a multi byte read.  Asking this device   |
| for more bytes than it has to give leaves it holding SDA   |
| low, which takes the whole bus down until the card is      |
| power cycled.                                              |
\*---------------------------------------------------------*/
static bool TestForOnixArcController(i2c_smbus_interface* bus, unsigned char address)
{
    return(bus->i2c_smbus_read_byte(address) >= 0);
}

DetectedControllers DetectOnixArcGPUControllers(i2c_smbus_interface* bus, uint8_t i2c_addr, const std::string& name)
{
    DetectedControllers detected_controllers;

    if(TestForOnixArcController(bus, i2c_addr))
    {
        OnixArcController*      controller      = new OnixArcController(bus, i2c_addr, name);
        RGBController_OnixArc*  rgb_controller  = new RGBController_OnixArc(controller);

        detected_controllers.push_back(rgb_controller);
    }
    else
    {
        LOG_DEBUG("[%s] No response at address 0x%02X", DETECTOR_NAME, i2c_addr);
    }

    return(detected_controllers);
}

REGISTER_I2C_PCI_DETECTOR("ONIX LUMI Intel Arc B580", DetectOnixArcGPUControllers, INTEL_VEN, INTEL_ARC_B580_DEV, ONIX_SUB_VEN, ONIX_LUMI_ARC_B580, ONIX_ARC_I2C_ADDRESS);
