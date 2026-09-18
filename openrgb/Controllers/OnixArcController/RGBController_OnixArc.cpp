/*---------------------------------------------------------*\
| RGBController_OnixArc.cpp                                 |
|                                                           |
|   RGBController for ONIX LUMI Intel Arc graphics cards     |
|                                                           |
|   This file is part of the OpenRGB project                |
|   SPDX-License-Identifier: GPL-2.0-or-later               |
\*---------------------------------------------------------*/

#include "RGBController_OnixArc.h"

/**------------------------------------------------------------------*\
    @name ONIX LUMI Intel Arc
    @category GPU
    @type I2C
    @save :x:
    @direct :white_check_mark:
    @effects :white_check_mark:
    @detectors DetectOnixArcGPUControllers
    @comment The lighting controller sits behind the card's AMC
        (Add-in card Management Controller) on the GPU's own internal
        I2C bus, at address 0x28.  On Linux that bus shows up as an
        i2c-dev node whose parent is the GPU's PCI device.

        The card generates every effect in firmware and offers no
        per-LED addressing, so the device is exposed as a single LED.
        Direct mode works by selecting the card's Custom mode once and
        then writing only the colour registers, which sustains at
        least 20 Hz.

        Settings are not persisted by the card; the vendor tool keeps
        them in its own configuration files.
\*-------------------------------------------------------------------*/

/*---------------------------------------------------------*\
| Effect parameters are 8 bit registers.  The vendor tool's  |
| defaults are used as the starting values.  The usable      |
| range of each one has not been characterised, so the full  |
| byte range is exposed.                                     |
\*---------------------------------------------------------*/
#define ONIX_SPEED_MIN              0x00
#define ONIX_SPEED_MAX              0xFF

enum
{
    ONIX_RGBCONTROLLER_MODE_DIRECT = 0,
    ONIX_RGBCONTROLLER_MODE_STATIC,
    ONIX_RGBCONTROLLER_MODE_BREATHING,
    ONIX_RGBCONTROLLER_MODE_RAINBOW,
    ONIX_RGBCONTROLLER_MODE_SERIAL,
    ONIX_RGBCONTROLLER_MODE_RUNWAY,
    ONIX_RGBCONTROLLER_MODE_ONECOLOR,
    ONIX_RGBCONTROLLER_MODE_BLOCK_STACKING,
};

RGBController_OnixArc::RGBController_OnixArc(OnixArcController* controller_ptr)
{
    controller                  = controller_ptr;

    name                        = controller->GetDeviceName();
    vendor                      = "ONIX";
    type                        = DEVICE_TYPE_GPU;
    description                 = "ONIX LUMI Intel Arc lighting";
    location                    = controller->GetDeviceLocation();

    mode Direct;
    Direct.name                 = "Direct";
    Direct.value                = ONIX_RGBCONTROLLER_MODE_DIRECT;
    Direct.flags                = MODE_FLAG_HAS_PER_LED_COLOR | MODE_FLAG_HAS_BRIGHTNESS;
    Direct.color_mode           = MODE_COLORS_PER_LED;
    Direct.brightness_min       = 0;
    Direct.brightness_max       = 0xFF;
    Direct.brightness           = ONIX_BRIGHTNESS_DEFAULT;
    modes.push_back(Direct);

    mode Static;
    Static.name                 = "Static";
    Static.value                = ONIX_RGBCONTROLLER_MODE_STATIC;
    Static.flags                = MODE_FLAG_HAS_MODE_SPECIFIC_COLOR | MODE_FLAG_HAS_BRIGHTNESS;
    Static.color_mode           = MODE_COLORS_MODE_SPECIFIC;
    Static.colors_min           = 1;
    Static.colors_max           = 1;
    Static.colors.resize(1);
    Static.brightness_min       = 0;
    Static.brightness_max       = 0xFF;
    Static.brightness           = ONIX_BRIGHTNESS_DEFAULT;
    modes.push_back(Static);

    mode Breathing;
    Breathing.name              = "Breathing";
    Breathing.value             = ONIX_RGBCONTROLLER_MODE_BREATHING;
    Breathing.flags             = MODE_FLAG_HAS_MODE_SPECIFIC_COLOR | MODE_FLAG_HAS_SPEED | MODE_FLAG_HAS_BRIGHTNESS;
    Breathing.color_mode        = MODE_COLORS_MODE_SPECIFIC;
    Breathing.colors_min        = 1;
    Breathing.colors_max        = 1;
    Breathing.colors.resize(1);
    Breathing.speed_min         = ONIX_SPEED_MIN;
    Breathing.speed_max         = ONIX_SPEED_MAX;
    Breathing.speed             = 6;
    Breathing.brightness_min    = 0;
    Breathing.brightness_max    = 0xFF;
    Breathing.brightness        = ONIX_BRIGHTNESS_DEFAULT;
    modes.push_back(Breathing);

    mode Rainbow;
    Rainbow.name                = "Rainbow";
    Rainbow.value               = ONIX_RGBCONTROLLER_MODE_RAINBOW;
    Rainbow.flags               = MODE_FLAG_HAS_SPEED | MODE_FLAG_HAS_BRIGHTNESS;
    Rainbow.color_mode          = MODE_COLORS_NONE;
    Rainbow.speed_min           = ONIX_SPEED_MIN;
    Rainbow.speed_max           = ONIX_SPEED_MAX;
    Rainbow.speed               = 5;
    Rainbow.brightness_min      = 0;
    Rainbow.brightness_max      = 0xFF;
    Rainbow.brightness          = ONIX_BRIGHTNESS_DEFAULT;
    modes.push_back(Rainbow);

    mode Serial;
    Serial.name                 = "Chroma Flow";
    Serial.value                = ONIX_RGBCONTROLLER_MODE_SERIAL;
    Serial.flags                = MODE_FLAG_HAS_SPEED | MODE_FLAG_HAS_BRIGHTNESS;
    Serial.color_mode           = MODE_COLORS_NONE;
    Serial.speed_min            = ONIX_SPEED_MIN;
    Serial.speed_max            = ONIX_SPEED_MAX;
    Serial.speed                = 16;
    Serial.brightness_min       = 0;
    Serial.brightness_max       = 0xFF;
    Serial.brightness           = ONIX_BRIGHTNESS_DEFAULT;
    modes.push_back(Serial);

    mode Runway;
    Runway.name                 = "Taxiway Glow";
    Runway.value                = ONIX_RGBCONTROLLER_MODE_RUNWAY;
    Runway.flags                = MODE_FLAG_HAS_SPEED | MODE_FLAG_HAS_BRIGHTNESS;
    Runway.color_mode           = MODE_COLORS_NONE;
    Runway.speed_min            = ONIX_SPEED_MIN;
    Runway.speed_max            = ONIX_SPEED_MAX;
    Runway.speed                = 10;
    Runway.brightness_min       = 0;
    Runway.brightness_max       = 0xFF;
    Runway.brightness           = ONIX_BRIGHTNESS_DEFAULT;
    modes.push_back(Runway);

    mode OneColor;
    OneColor.name               = "One Color";
    OneColor.value              = ONIX_RGBCONTROLLER_MODE_ONECOLOR;
    OneColor.flags              = MODE_FLAG_HAS_SPEED | MODE_FLAG_HAS_BRIGHTNESS;
    OneColor.color_mode         = MODE_COLORS_NONE;
    OneColor.speed_min          = ONIX_SPEED_MIN;
    OneColor.speed_max          = ONIX_SPEED_MAX;
    OneColor.speed              = 10;
    OneColor.brightness_min     = 0;
    OneColor.brightness_max     = 0xFF;
    OneColor.brightness         = ONIX_BRIGHTNESS_DEFAULT;
    modes.push_back(OneColor);

    mode Stacking;
    Stacking.name               = "Stacking";
    Stacking.value              = ONIX_RGBCONTROLLER_MODE_BLOCK_STACKING;
    Stacking.flags              = MODE_FLAG_HAS_SPEED | MODE_FLAG_HAS_BRIGHTNESS;
    Stacking.color_mode         = MODE_COLORS_NONE;
    Stacking.speed_min          = ONIX_SPEED_MIN;
    Stacking.speed_max          = ONIX_SPEED_MAX;
    Stacking.speed              = 10;
    Stacking.brightness_min     = 0;
    Stacking.brightness_max     = 0xFF;
    Stacking.brightness         = ONIX_BRIGHTNESS_DEFAULT;
    modes.push_back(Stacking);

    SetupZones();
}

RGBController_OnixArc::~RGBController_OnixArc()
{
    delete controller;
}

void RGBController_OnixArc::SetupZones()
{
    /*-----------------------------------------------------*\
    | The card exposes no per-LED addressing, so a single    |
    | LED stands for the whole illuminated area.             |
    \*-----------------------------------------------------*/
    zone lighting_zone;
    lighting_zone.name          = "Graphics Card";
    lighting_zone.type          = ZONE_TYPE_SINGLE;
    lighting_zone.leds_min      = 1;
    lighting_zone.leds_max      = 1;
    lighting_zone.leds_count    = 1;
    zones.push_back(lighting_zone);

    led lighting_led;
    lighting_led.name           = "Graphics Card";
    leds.push_back(lighting_led);

    SetupColors();
}

void RGBController_OnixArc::ApplyMode(const mode& active, RGBColor color)
{
    unsigned char red   = RGBGetRValue(color);
    unsigned char green = RGBGetGValue(color);
    unsigned char blue  = RGBGetBValue(color);

    /*-----------------------------------------------------*\
    | Order matters and each step is its own transaction.    |
    | Brightness has to be reapplied after a mode change:    |
    | a mode entered for the first time comes up dark.       |
    \*-----------------------------------------------------*/
    switch(active.value)
    {
        case ONIX_RGBCONTROLLER_MODE_DIRECT:
        case ONIX_RGBCONTROLLER_MODE_STATIC:
            controller->SetMode(ONIX_MODE_CUSTOM);
            controller->SetBrightness((unsigned char)active.brightness);
            controller->SetCustomColor(red, green, blue);
            break;

        case ONIX_RGBCONTROLLER_MODE_BREATHING:
            controller->SetMode(ONIX_MODE_BREATHING);
            controller->SetBrightness((unsigned char)active.brightness);
            controller->SetBreathingColor(red, green, blue);
            controller->SetRegister(ONIX_REG_BREATHING_TEMPO, (unsigned char)active.speed);
            break;

        case ONIX_RGBCONTROLLER_MODE_RAINBOW:
            controller->SetMode(ONIX_MODE_RAINBOW);
            controller->SetBrightness((unsigned char)active.brightness);
            controller->SetRegister(ONIX_REG_RAINBOW_SPEED, (unsigned char)active.speed);
            break;

        case ONIX_RGBCONTROLLER_MODE_SERIAL:
            controller->SetMode(ONIX_MODE_SERIAL);
            controller->SetBrightness((unsigned char)active.brightness);
            controller->SetRegister(ONIX_REG_SERIAL_SPEED, (unsigned char)active.speed);
            break;

        case ONIX_RGBCONTROLLER_MODE_RUNWAY:
            controller->SetMode(ONIX_MODE_RUNWAY);
            controller->SetBrightness((unsigned char)active.brightness);
            controller->SetRegister(ONIX_REG_RUNWAY_RESPONSE, (unsigned char)active.speed);
            break;

        case ONIX_RGBCONTROLLER_MODE_ONECOLOR:
            controller->SetMode(ONIX_MODE_ONECOLOR);
            controller->SetBrightness((unsigned char)active.brightness);
            controller->SetRegister(ONIX_REG_ONECOLOR_RESPONSE, (unsigned char)active.speed);
            break;

        case ONIX_RGBCONTROLLER_MODE_BLOCK_STACKING:
            controller->SetMode(ONIX_MODE_BLOCK_STACKING);
            controller->SetBrightness((unsigned char)active.brightness);
            controller->SetRegister(ONIX_REG_STACKING_SPEED, (unsigned char)active.speed);
            break;
    }
}

void RGBController_OnixArc::DeviceUpdateLEDs()
{
    const mode& active = modes[active_mode];

    if(active.value == ONIX_RGBCONTROLLER_MODE_DIRECT)
    {
        /*-------------------------------------------------*\
        | Direct mode is the hot path: the card is already   |
        | in Custom mode, so only the colour registers get   |
        | rewritten.  Touching the mode register here would  |
        | restart the effect on every frame.                 |
        \*-------------------------------------------------*/
        controller->SetCustomColor(RGBGetRValue(colors[0]),
                                   RGBGetGValue(colors[0]),
                                   RGBGetBValue(colors[0]));
    }
    else
    {
        ApplyMode(active, active.colors.size() > 0 ? active.colors[0] : colors[0]);
    }
}

void RGBController_OnixArc::DeviceUpdateZoneLEDs(int /*zone*/)
{
    DeviceUpdateLEDs();
}

void RGBController_OnixArc::DeviceUpdateSingleLED(int /*led*/)
{
    DeviceUpdateLEDs();
}

void RGBController_OnixArc::DeviceUpdateMode()
{
    const mode& active = modes[active_mode];

    ApplyMode(active, active.colors.size() > 0 ? active.colors[0] : colors[0]);
}
