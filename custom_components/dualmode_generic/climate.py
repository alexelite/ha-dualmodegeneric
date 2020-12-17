"""
Adds support for generic thermostat units that have both heating and cooling.

Originally based on the script at this thread:
https://community.home-assistant.io/t/heat-cool-generic-thermostat/76443/2

Modified to better conform to modern Home Assistant custom_component style.
"""
import asyncio
import logging

import voluptuous as vol

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_PRESET_MODE,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_OFF,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    PRESET_AWAY,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    PRESET_NONE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_NAME,
    CONF_SENSOR_TYPE,
    EVENT_HOMEASSISTANT_START,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
)
from homeassistant.core import DOMAIN as HA_DOMAIN, callback
from homeassistant.helpers import condition
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity

_LOGGER = logging.getLogger(__name__)

DEFAULT_TOLERANCE = 0.3
DEFAULT_NAME = "Generic Thermostat"

CONF_HEATER = "heater"
CONF_COOLER = "cooler"
CONF_REVERSE_CYCLE = "reverse_cycle"
CONF_SENSOR = "target_sensor"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"

CONF_SENSOR_MODE = "sensor_mode"
CONF_FLOOR_SENSOR = "floor_sensor"
CONF_FS_COOL_MIN_TEMP = "fs_cool_min_temp"
CONF_FS_COOL_MAX_TEMP = "fs_cool_max_temp"
CONF_FS_HEAT_MIN_TEMP = "fs_heat_min_temp"
CONF_FS_HEAT_MAX_TEMP = "fs_heat_max_temp"
SENSOR_MODE_AMBIENT = "ambient"
SENSOR_MODE_FLOOR = "floor"
SENSOR_MODE_SMART = "smart"


CONF_TARGET_TEMP = "target_temp"
CONF_MIN_DUR = "min_cycle_duration"
CONF_COLD_TOLERANCE = "cold_tolerance"
CONF_HOT_TOLERANCE = "hot_tolerance"
CONF_KEEP_ALIVE = "keep_alive"
CONF_INITIAL_HVAC_MODE = "initial_hvac_mode"
CONF_AWAY_TEMP = "away_temp"
CONF_PRECISION = "precision"
SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HEATER): cv.entity_id,
        vol.Required(CONF_COOLER): cv.entity_id,
        vol.Required(CONF_SENSOR): cv.entity_id,
        vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MIN_DUR): vol.All(cv.time_period, cv.positive_timedelta),
        vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_FLOOR_SENSOR): cv.entity_id,
        vol.Optional(CONF_FS_COOL_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_FS_COOL_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_FS_HEAT_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_FS_HEAT_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_SENSOR_MODE, default="ambient"): vol.In(
            [SENSOR_MODE_AMBIENT, SENSOR_MODE_FLOOR, SENSOR_MODE_SMART]
        ),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_REVERSE_CYCLE, default=False): cv.boolean,
        vol.Optional(CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(float),
        vol.Optional(CONF_HOT_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(float),
        vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
        vol.Optional(CONF_KEEP_ALIVE): vol.All(cv.time_period, cv.positive_timedelta),
        vol.Optional(CONF_INITIAL_HVAC_MODE): vol.In(
            [HVAC_MODE_COOL, HVAC_MODE_HEAT, HVAC_MODE_OFF]
        ),
        vol.Optional(CONF_AWAY_TEMP): vol.Coerce(float),
        vol.Optional(CONF_PRECISION): vol.In(
            [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE]
        ),
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the dual mode generic thermostat platform."""
    name = config.get(CONF_NAME)
    heater_entity_id = config.get(CONF_HEATER)
    cooler_entity_id = config.get(CONF_COOLER)
    sensor_entity_id = config.get(CONF_SENSOR)
    reverse_cycle = config.get(CONF_REVERSE_CYCLE)
    min_temp = config.get(CONF_MIN_TEMP)
    max_temp = config.get(CONF_MAX_TEMP)
    sensor_mode = config.get(CONF_SENSOR_MODE)
    floor_sensor_entity_id = config.get(CONF_FLOOR_SENSOR)
    fs_cool_min_temp = config.get(CONF_FS_COOL_MIN_TEMP)
    fs_cool_max_temp = config.get(CONF_FS_COOL_MAX_TEMP)
    fs_heat_min_temp = config.get(CONF_FS_HEAT_MIN_TEMP)
    fs_heat_max_temp = config.get(CONF_FS_HEAT_MAX_TEMP)
    target_temp = config.get(CONF_TARGET_TEMP)
    min_cycle_duration = config.get(CONF_MIN_DUR)
    cold_tolerance = config.get(CONF_COLD_TOLERANCE)
    hot_tolerance = config.get(CONF_HOT_TOLERANCE)
    keep_alive = config.get(CONF_KEEP_ALIVE)
    initial_hvac_mode = config.get(CONF_INITIAL_HVAC_MODE)
    away_temp = config.get(CONF_AWAY_TEMP)
    precision = config.get(CONF_PRECISION)
    unit = hass.config.units.temperature_unit

    async_add_entities(
        [
            DualModeGenericThermostat(
                name,
                heater_entity_id,
                cooler_entity_id,
                sensor_entity_id,
                reverse_cycle,
                min_temp,
                max_temp,
                sensor_mode,
                floor_sensor_entity_id,
                fs_cool_min_temp,
                fs_cool_max_temp,
                fs_heat_min_temp,
                fs_heat_max_temp,
                target_temp,
                min_cycle_duration,
                cold_tolerance,
                hot_tolerance,
                keep_alive,
                initial_hvac_mode,
                away_temp,
                precision,
                unit,
            )
        ]
    )


class DualModeGenericThermostat(ClimateEntity, RestoreEntity):
    """Representation of a Generic Thermostat device."""

    def __init__(
        self,
        name,
        heater_entity_id,
        cooler_entity_id,
        sensor_entity_id,
        reverse_cycle,
        min_temp,
        max_temp,
        sensor_mode,
        floor_sensor_entity_id,
        fs_cool_min_temp,
        fs_cool_max_temp,
        fs_heat_min_temp,
        fs_heat_max_temp,
        target_temp,
        min_cycle_duration,
        cold_tolerance,
        hot_tolerance,
        keep_alive,
        initial_hvac_mode,
        away_temp,
        precision,
        unit,
    ):
        """Initialize the thermostat."""
        self._name = name
        self.heater_entity_id = heater_entity_id
        self.cooler_entity_id = cooler_entity_id
        self.sensor_entity_id = sensor_entity_id
        self.reverse_cycle = reverse_cycle
        self.min_cycle_duration = min_cycle_duration
        self._cold_tolerance = cold_tolerance
        self._hot_tolerance = hot_tolerance
        self._keep_alive = keep_alive
        self._hvac_mode = initial_hvac_mode
        self._saved_target_temp = target_temp or away_temp
        self._temp_precision = precision
        self._hvac_list = [HVAC_MODE_COOL, HVAC_MODE_HEAT, HVAC_MODE_OFF]
        self._active = False
        self._cur_temp = None
        self._cur_floor_temp = None
        self._temp_lock = asyncio.Lock()
        self._min_temp = min_temp
        self._max_temp = max_temp
        self.sensor_mode = sensor_mode
        self.floor_sensor_entity_id = floor_sensor_entity_id
        self._fs_cool_min_temp = fs_cool_min_temp
        self._fs_cool_max_temp = fs_cool_max_temp
        self._fs_heat_min_temp = fs_heat_min_temp
        self._fs_heat_max_temp = fs_heat_max_temp
        self._target_temp = target_temp
        self._unit = unit
        self._support_flags = SUPPORT_FLAGS
        if away_temp:
            self._support_flags = SUPPORT_FLAGS | SUPPORT_PRESET_MODE
        self._away_temp = away_temp
        self._is_away = False

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Add listener
        async_track_state_change(
            self.hass, self.sensor_entity_id, self._async_sensor_changed
        )

        if self.floor_sensor_entity_id is not None:
            async_track_state_change(
                self.hass, self.floor_sensor_entity_id, self._async_floor_sensor_changed
            )
        async_track_state_change(
            self.hass, self.heater_entity_id, self._async_switch_changed
        )
        async_track_state_change(
            self.hass, self.cooler_entity_id, self._async_switch_changed
        )

        if self._keep_alive:
            async_track_time_interval(
                self.hass, self._async_control_heating, self._keep_alive
            )

        @callback
        def _async_startup(event):
            """Init on startup."""
            sensor_state = self.hass.states.get(self.sensor_entity_id)
            if sensor_state and sensor_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                _LOGGER.info("Init on startup.")
                self._async_update_temp(sensor_state)
                self._async_update_floor_temp(sensor_state)  # check if needed

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)

        # Check If we have an old state
        old_state = await self.async_get_last_state()
        if old_state is not None:
            # If we have no initial temperature, restore
            if self._target_temp is None:
                # If we have a previously saved temperature
                if old_state.attributes.get(ATTR_TEMPERATURE) is None:
                    if self._hvac_mode == HVAC_MODE_COOL:
                        self._target_temp = self.max_temp
                    else:
                        self._target_temp = self.min_temp
                    _LOGGER.warning(
                        "Undefined target temperature," "falling back to %s",
                        self._target_temp,
                    )
                else:
                    self._target_temp = float(old_state.attributes[ATTR_TEMPERATURE])
            if old_state.attributes.get(ATTR_PRESET_MODE) == PRESET_AWAY:
                self._is_away = True
            if not self._hvac_mode and old_state.state:
                self._hvac_mode = old_state.state

        else:
            # No previous state, try and restore defaults
            if self._target_temp is None:
                if self._hvac_mode == HVAC_MODE_COOL:
                    self._target_temp = self.max_temp
                else:
                    self._target_temp = self.min_temp
            _LOGGER.warning(
                "No previously saved temperature, setting to %s", self._target_temp
            )

        # Set default state to off
        if not self._hvac_mode:
            self._hvac_mode = HVAC_MODE_OFF

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def precision(self):
        """Return the precision of the system."""
        if self._temp_precision is not None:
            return self._temp_precision
        return super().precision

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def current_temperature(self):
        """Return the sensor temperature."""
        return self._cur_temp

    @property
    def current_floor_temperature(self):
        """Return the sensor temperature."""
        return self._cur_floor_temp

    @property
    def hvac_mode(self):
        """Return current operation."""
        return self._hvac_mode

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported.

        Need to be one of CURRENT_HVAC_*.
        """
        if self._hvac_mode == HVAC_MODE_OFF:
            return CURRENT_HVAC_OFF
        if not self._is_device_active:
            return CURRENT_HVAC_IDLE
        if self._hvac_mode == HVAC_MODE_COOL:
            return CURRENT_HVAC_COOL
        if self._hvac_mode == HVAC_MODE_HEAT:
            return CURRENT_HVAC_HEAT
        return CURRENT_HVAC_IDLE

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._hvac_list

    @property
    def preset_mode(self):
        """Return the current preset mode, e.g., home, away, temp."""
        return PRESET_AWAY if self._is_away else PRESET_NONE

    @property
    def preset_modes(self):
        """Return a list of available preset modes or PRESET_NONE if _away_temp is undefined."""
        return [PRESET_NONE, PRESET_AWAY] if self._away_temp else PRESET_NONE

    async def async_set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        if hvac_mode == HVAC_MODE_HEAT:
            self._hvac_mode = HVAC_MODE_HEAT
            if self._is_device_active and not self.reverse_cycle:
                await self._async_cooler_turn_off()
            await self._async_control_heating(force=True)
        elif hvac_mode == HVAC_MODE_COOL:
            self._hvac_mode = HVAC_MODE_COOL
            if self._is_device_active and not self.reverse_cycle:
                await self._async_heater_turn_off()
            await self._async_control_heating(force=True)
        elif hvac_mode == HVAC_MODE_OFF:
            self._hvac_mode = HVAC_MODE_OFF
            if self._is_device_active:
                await self._async_heater_turn_off()
                await self._async_cooler_turn_off()
        else:
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return
        # Ensure we update the current operation after changing the mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._target_temp = temperature
        await self._async_control_heating(force=True)
        self.async_write_ha_state()

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if self._min_temp is not None:
            return self._min_temp

        # get default temp from super class
        return super().min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self._max_temp is not None:
            return self._max_temp

        # Get default temp from super class
        return super().max_temp

    @property
    def fs_cool_min_temp(self):
        """Return the minimum temperature."""
        if self._fs_cool_min_temp is not None:
            return self._fs_cool_min_temp

        # get default temp from super class
        return 16  # super().min_temp

    @property
    def fs_cool_max_temp(self):
        """Return the maximum temperature."""
        if self._fs_cool_max_temp is not None:
            return self._fs_cool_max_temp

        # Get default temp from super class
        return 20  # super().max_temp

    @property
    def fs_heat_min_temp(self):
        """Return the minimum temperature."""
        if self._fs_heat_min_temp is not None:
            return self._fs_heat_min_temp

        # get default temp from super class
        return 24  # super().min_temp

    @property
    def fs_heat_max_temp(self):
        """Return the maximum temperature."""
        if self._fs_heat_max_temp is not None:
            return self._fs_heat_max_temp

        # Get default temp from super class
        return 28  # super().max_temp

    async def _async_sensor_changed(self, entity_id, old_state, new_state):
        """Handle temperature changes."""
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        self._async_update_temp(new_state)
        await self._async_control_heating()
        self.async_write_ha_state()

    async def _async_floor_sensor_changed(self, entity_id, old_state, new_state):
        """Handle temperature changes."""
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        self._async_update_floor_temp(new_state)
        await self._async_control_heating()
        self.async_write_ha_state()

    @callback
    def _async_switch_changed(self, entity_id, old_state, new_state):
        """Handle heater switch state changes."""
        if new_state is None:
            return
        self.async_write_ha_state()

    @callback
    def _async_update_temp(self, state):
        """Update thermostat with latest state from sensor."""
        try:
            self._cur_temp = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s", ex)
        else:
            _LOGGER.info("Update thermostat with latest state from sensor")

    @callback
    def _async_update_floor_temp(self, state):
        """Update thermostat with latest state from floor sensor."""
        try:
            self._cur_floor_temp = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s", ex)
        else:
            _LOGGER.info("Update thermostat with latest state from floor sensor")

    async def _async_control_heating(self, time=None, force=False):
        """Check if we need to turn heating on or off."""
        async with self._temp_lock:
            if not self._active and None not in (self._cur_temp, self._target_temp):
                self._active = True
                _LOGGER.info(
                    "Obtained current and target temperature. "
                    "Generic Dual-mode thermostat active. %s, %s",
                    self._cur_temp,
                    self._target_temp,
                )

            if not self._active or self._hvac_mode == HVAC_MODE_OFF:
                return

            if not force and time is None:
                # If the `force` argument is True, we
                # ignore `min_cycle_duration`.
                # If the `time` argument is not none, we were invoked for
                # keep-alive purposes, and `min_cycle_duration` is irrelevant.
                if self.min_cycle_duration:
                    entity = (
                        self.cooler_entity_id
                        if self._hvac_mode == HVAC_MODE_COOL
                        else self.heater_entity_id
                    )

                    if self._is_device_active:
                        current_state = STATE_ON
                    else:
                        current_state = HVAC_MODE_OFF
                    long_enough = condition.state(
                        self.hass,
                        entity,
                        current_state,
                        self.min_cycle_duration,
                    )
                    if not long_enough:
                        return

            # self._hvac_mode can only be HVAC_MODE_HEAT or HVAC_MODE_COOL at this point
            if self.sensor_mode == SENSOR_MODE_SMART:
                if self._hvac_mode == HVAC_MODE_HEAT:
                    too_cold = (
                        self._fs_heat_min_temp
                        >= self._cur_floor_temp + self._cold_tolerance
                        or (
                            self._target_temp >= self._cur_temp + self._cold_tolerance
                            and self._fs_heat_max_temp
                            >= self._cur_floor_temp + self._cold_tolerance
                        )
                    )
                    too_hot = (
                        self._cur_floor_temp
                        >= self._fs_heat_max_temp + self._hot_tolerance
                        or (
                            self._cur_floor_temp
                            >= self._fs_heat_min_temp + self._hot_tolerance
                            and self._cur_temp
                            >= self._target_temp + self._hot_tolerance
                        )
                    )
                elif self._hvac_mode == HVAC_MODE_COOL:
                    too_cold = (
                        self._cur_floor_temp + self._cold_tolerance
                        <= self._fs_cool_min_temp
                        or (
                            self._fs_cool_max_temp
                            >= self._cur_floor_temp + self._cold_tolerance
                            and self._target_temp
                            >= self._cur_temp + self._cold_tolerance
                        )
                    )
                    too_hot = (
                        self._cur_floor_temp
                        >= self._fs_cool_max_temp + self._hot_tolerance
                        or (
                            self._cur_temp >= self._target_temp + self._hot_tolerance
                            and self._cur_floor_temp
                            >= self._fs_cool_min_temp + self._hot_tolerance
                        )
                    )
            elif self.sensor_mode == SENSOR_MODE_FLOOR:
                if self._hvac_mode == HVAC_MODE_HEAT:
                    too_cold = (
                        self._fs_heat_min_temp
                        >= self._cur_floor_temp + self._cold_tolerance
                        or (
                            self._target_temp
                            >= self._cur_floor_temp + self._cold_tolerance
                            and self._fs_heat_max_temp
                            >= self._cur_floor_temp + self._cold_tolerance
                        )
                    )
                    too_hot = (
                        self._cur_floor_temp
                        >= self._fs_heat_max_temp + self._hot_tolerance
                        or (
                            self._cur_floor_temp
                            >= self._fs_heat_min_temp + self._hot_tolerance
                            and self._cur_floor_temp
                            >= self._target_temp + self._hot_tolerance
                        )
                    )
                elif self._hvac_mode == HVAC_MODE_COOL:
                    too_cold = (
                        self._fs_cool_min_temp
                        >= self._cur_floor_temp + self._cold_tolerance
                        or (
                            self._fs_cool_max_temp
                            >= self._cur_floor_temp + self._cold_tolerance
                            and self._target_temp
                            >= self._cur_floor_temp + self._cold_tolerance
                        )
                    )
                    too_hot = (
                        self._cur_floor_temp
                        >= self._fs_cool_max_temp + self._hot_tolerance
                        or (
                            self._cur_floor_temp
                            >= self._target_temp + self._hot_tolerance
                            and self._target_temp
                            > self._fs_cool_min_temp + self._hot_tolerance
                        )
                    )
            else:  # self.sensor_mode == SENSOR_MODE_AMBIENT:
                too_cold = self._target_temp >= self._cur_temp + self._cold_tolerance
                too_hot = self._cur_temp >= self._target_temp + self._hot_tolerance
            if self._is_device_active:  # when to turn off
                if too_cold and self._hvac_mode == HVAC_MODE_COOL:
                    _LOGGER.info("Turning off cooler %s", self.cooler_entity_id)
                    await self._async_cooler_turn_off()
                elif too_hot and self._hvac_mode == HVAC_MODE_HEAT:
                    _LOGGER.info("Turning off heater %s", self.heater_entity_id)
                    await self._async_heater_turn_off()
                elif time is not None:
                    # The time argument is passed only in keep-alive case
                    _LOGGER.info(
                        "Keep-alive - Turning on heater heater %s",
                        self.heater_entity_id
                        if self._hvac_mode == HVAC_MODE_HEAT
                        else self.cooler_entity_id,
                    )
                    if self._hvac_mode == HVAC_MODE_COOL:
                        await self._async_cooler_turn_on()
                    elif self._hvac_mode == HVAC_MODE_HEAT:
                        await self._async_heater_turn_on()
            else:  # when to turn on
                if too_hot and self._hvac_mode == HVAC_MODE_COOL:
                    _LOGGER.info("Turning on cooler %s", self.cooler_entity_id)
                    await self._async_cooler_turn_on()
                elif too_cold and self._hvac_mode == HVAC_MODE_HEAT:
                    _LOGGER.info("Turning on heater %s", self.heater_entity_id)
                    await self._async_heater_turn_on()
                elif time is not None:
                    # The time argument is passed only in keep-alive case
                    _LOGGER.info(
                        "Keep-alive - Turning off heater %s",
                        self.heater_entity_id
                        if self._hvac_mode == HVAC_MODE_HEAT
                        else self.cooler_entity_id,
                    )
                    if self._hvac_mode == HVAC_MODE_COOL:
                        await self._async_cooler_turn_off()
                    elif self._hvac_mode == HVAC_MODE_HEAT:
                        await self._async_heater_turn_off()

    @property
    def _is_device_active(self):
        """If the toggleable device is currently active."""
        return self.hass.states.is_state(
            self.heater_entity_id, STATE_ON
        ) or self.hass.states.is_state(self.cooler_entity_id, STATE_ON)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags

    async def _async_heater_turn_on(self):
        """Turn heater toggleable device on."""
        data = {ATTR_ENTITY_ID: self.heater_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_ON, data)

    async def _async_heater_turn_off(self):
        """Turn heater toggleable device off."""
        data = {ATTR_ENTITY_ID: self.heater_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_OFF, data)

    async def _async_cooler_turn_on(self):
        """Turn cooler toggleable device on."""
        data = {ATTR_ENTITY_ID: self.cooler_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_ON, data)

    async def _async_cooler_turn_off(self):
        """Turn cooler toggleable device off."""
        data = {ATTR_ENTITY_ID: self.cooler_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_OFF, data)

    async def async_set_preset_mode(self, preset_mode: str):
        """Set new preset mode."""
        if preset_mode == PRESET_AWAY and not self._is_away:
            self._is_away = True
            self._saved_target_temp = self._target_temp
            self._target_temp = self._away_temp
            await self._async_control_heating(force=True)
        elif preset_mode == PRESET_NONE and self._is_away:
            self._is_away = False
            self._target_temp = self._saved_target_temp
            await self._async_control_heating(force=True)

        self.async_write_ha_state()
