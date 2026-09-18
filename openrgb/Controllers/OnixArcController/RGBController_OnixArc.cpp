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
/*---------------------------------------------------------*\
| Values from 1 to 64 were all confirmed to keep the effects  |
| running.  The range above that was never exercised, so the  |
| slider stops where the evidence does.  The perceived        |
| difference across this range is subtle.                     |
\*---------------------------------------------------------*/
#define ONIX_SPEED_MIN              0x01
#define ONIX_SPEED_MAX              0x40

/*---------------------------------------------------------*\
| Every animated mode carries a "response" register in        |
| addition to its speed.  It is not optional: with it unset   |
| the mode lights up but never animates.  The vendor tool's    |
| defaults are written whenever a mode is selected.           |
\*---------------------------------------------------------*/
#define ONIX_RAINBOW_RESPONSE_DEFAULT   0x02
#define ONIX_RUNWAY_RESPONSE_DEFAULT    0x0A
#define ONIX_RUNWAY_CHASER_DEFAULT      0x01
#define ONIX_SERIAL_RESPONSE_DEFAULT    0x02

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
    /*-----------------------------------------------------*\
    | The base class runs a device thread; it has to be      |
    | stopped here, before the base destructor runs.         |
    \*-----------------------------------------------------*/
    Shutdown();

    delete controller;
}

void RGBController_OnixArc::SetupZones()
{
    /*-----------------------------------------------------*\
    | The strip holds 14 LEDs, which register 0x27 declares   |
    | to the firmware, but nothing in the protocol addresses  |
    | them individually: colour goes to the whole strip at    |
    | once.  A single LED is therefore the honest             |
    | representation, rather than 14 that always match.       |
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
            controller->SetRegister(ONIX_REG_RAINBOW_RESPONSE, ONIX_RAINBOW_RESPONSE_DEFAULT);
            controller->SetRegister(ONIX_REG_RAINBOW_SPEED, (unsigned char)active.speed);
            break;

        case ONIX_RGBCONTROLLER_MODE_SERIAL:
            controller->SetMode(ONIX_MODE_SERIAL);
            controller->SetBrightness((unsigned char)active.brightness);
            controller->SetRegister(ONIX_REG_SERIAL_RESPONSE, ONIX_SERIAL_RESPONSE_DEFAULT);
            controller->SetRegister(ONIX_REG_SERIAL_SPEED, (unsigned char)active.speed);
            break;

        case ONIX_RGBCONTROLLER_MODE_RUNWAY:
            controller->SetMode(ONIX_MODE_RUNWAY);
            controller->SetBrightness((unsigned char)active.brightness);
            controller->SetRegister(ONIX_REG_RUNWAY_RESPONSE, ONIX_RUNWAY_RESPONSE_DEFAULT);
            controller->SetRegister(ONIX_REG_RUNWAY_CHASER, ONIX_RUNWAY_CHASER_DEFAULT);
            controller->SetRegister(ONIX_REG_RUNWAY_INTERVAL, (unsigned char)active.speed);
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

    /*-----------------------------------------------------*\
    | Only colour registers are touched here.  Rewriting the |
    | mode register restarts the hardware effect, and        |
    | OpenRGB calls this right after DeviceUpdateMode and    |
    | again on every colour change, so re-applying the whole |
    | mode would restart the animation constantly.           |
    \*-----------------------------------------------------*/
    switch(active.value)
    {
        case ONIX_RGBCONTROLLER_MODE_DIRECT:
            controller->SetCustomColor(RGBGetRValue(colors[0]),
                                       RGBGetGValue(colors[0]),
                                       RGBGetBValue(colors[0]));
            break;

        case ONIX_RGBCONTROLLER_MODE_STATIC:
            if(active.colors.size() > 0)
            {
                controller->SetCustomColor(RGBGetRValue(active.colors[0]),
                                           RGBGetGValue(active.colors[0]),
                                           RGBGetBValue(active.colors[0]));
            }
            break;

        case ONIX_RGBCONTROLLER_MODE_BREATHING:
            if(active.colors.size() > 0)
            {
                controller->SetBreathingColor(RGBGetRValue(active.colors[0]),
                                              RGBGetGValue(active.colors[0]),
                                              RGBGetBValue(active.colors[0]));
            }
            break;

        default:
            /*---------------------------------------------*\
            | The remaining modes generate their own colours |
            | in firmware and have nothing to update.        |
            \*---------------------------------------------*/
            break;
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
