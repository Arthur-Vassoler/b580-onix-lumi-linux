/*---------------------------------------------------------*\
| RGBController_OnixArc.h                                   |
|                                                           |
|   RGBController for ONIX LUMI Intel Arc graphics cards     |
|                                                           |
|   This file is part of the OpenRGB project                |
|   SPDX-License-Identifier: GPL-2.0-or-later               |
\*---------------------------------------------------------*/

#pragma once

#include "RGBController.h"
#include "OnixArcController.h"

class RGBController_OnixArc : public RGBController
{
public:
    RGBController_OnixArc(OnixArcController* controller_ptr);
    ~RGBController_OnixArc();

    void        SetupZones();

    void        DeviceUpdateLEDs();
    void        DeviceUpdateZoneLEDs(int zone);
    void        DeviceUpdateSingleLED(int led);

    void        DeviceUpdateMode();

private:
    OnixArcController*  controller;

    void        ApplyMode(const mode& active, RGBColor color);
};
