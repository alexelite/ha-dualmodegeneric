# Home Assistant - Dual Mode Underfloor Thermostat with floor sensor
Based on [zacs/ha-dualmodegeneric](https://github.com/zacs/ha-dualmodegeneric)

## About
I have ambient temperature sensors and floor temperature sensors in every room and I want to control the room temperature based on ambient air temperature and also set limit for floor temperature, idividualy for heating and for cooling.
This is the first time I used python so please check it before you use it. For the moment I have it set up as 9 thermostats and all is good, but definitly needs more work. At the moment there are no check for min/max values, for example if max is lower than min.

## Installation (Manual)
1. Download this repository as a ZIP (green button, top right) and unzip the archive
2. Copy `/custom_components/dualmode_generic` to your `<config_dir>/custom_components/` directory
   * You will need to create the `custom_components` folder if it does not exist
   * On Hassio the final location will be `/config/custom_components/dualmode_generic`
   * On Hassbian the final location will be `/home/homeassistant/.homeassistant/custom_components/dualmode_generic`

## Configuration
Add the following to your configuration file

```yaml
climate:
  - platform: dualmode_generic
    name: My Thermostat
    heater: switch.heater
    cooler: switch.fan
    target_sensor: sensor.my_temp_sensor
    reverse_cycle: true
    floor_sensor: sensor.my_floor_temp_sensor
    sensor_mode: smart
    fs_cool_min_temp: 20
    fs_cool_max_temp: 24
    fs_heat_min_temp: 24
    fs_heat_max_temp: 28
```

The component shares the same configuration variables as the standard `generic_thermostat`, with three exceptions:
* A `cooler` variable has been added where you can specify the `entity_id` of your switch for a cooling unit (AC, fan, etc).
* If the cooling and heating unit are the same device (e.g. a reverse cycle air conditioner) setting `reverse_cycle` to `true` will ensure the device isn't switched off entirely when switching modes
* The `ac_mode` variable has been removed, since it makes no sense for this use case.
* `floor_sensor` variable specifies the `entity_id` for the floor temperature sensor.
* The `sensor_mode` can change the sensor used for controling the outputs. Values accepted are `ambient` (default), `floor`, `smart`.
  `ambient` uses only the air temperature, same as generic thermostat.
  `floor` uses only the floor sensor instead of ambient sensor with the aditional limits.
  `smart` uses both sensors. Air temperature for target temperature and floor sensors for floor temperature limits. Ambient temperature is valid only when floor temperature is within limits. 
* The `fs_cool_min_temp` and `fs_cool_max_temp` define the limits for cooling mode and `fs_heat_min_temp` and `fs_heat_max_temp` define the limits for heating mode.
* `humidity_sensor` entity_id, will be used in the future to stop cooling if value above safety threshold, for the moment it is just passed as an attribute for the climate entity to be used in lovelace card
* `window_switch` entity_id, for the moment it is just passed as an attribute for the climate entity to be used in lovelace card

Refer to the [Generic Thermostat documentation](https://www.home-assistant.io/components/generic_thermostat/) for details on the rest of the variables. This component doesn't change their functionality.

## Behavior

* The thermostat will follow standard mode-based behavior: if set to "cool," the only switch which can be activated is the `cooler`. This means if the target temperature is higher than the actual temperateure, the `heater` will _not_ start. Vice versa is also true.

* Keepalive logic has been updated to be aware of the mode in current use, so should function as expected.

* By default, the component will restore the last state of the thermostat prior to a restart.

* While `heater`/`cooler` are documented to be `switch`es, they can also be `input_boolean`s if necessary.


## Reporting an Issue
1. Setup your logger to print debug messages for this component using:
```yaml
logger:
  default: info
  logs:
    custom_components.dualmode_generic: debug
```
2. Restart HA
3. Verify you're still having the issue
4. File an issue in this Github Repository containing your HA log (Developer section > Info > Load Full Home Assistant Log)
   * You can paste your log file at pastebin https://pastebin.com/ and submit a link.
   * Please include details about your setup (Pi, NUC, etc, docker?, HASSOS?)
   * The log file can also be found at `/<config_dir>/home-assistant.log`
