"""Support for monitoring a Sense energy sensor."""
from datetime import timedelta
import logging

from sense_energy import SenseAPITimeoutException

from homeassistant.const import ENERGY_KILO_WATT_HOUR, POWER_WATT
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

from .const import DOMAIN, SENSE_DATA

_LOGGER = logging.getLogger(__name__)

ACTIVE_NAME = "Energy"
ACTIVE_TYPE = "active"

CONSUMPTION_NAME = "Usage"

ICON = "mdi:flash"

MIN_TIME_BETWEEN_DAILY_UPDATES = timedelta(seconds=300)

PRODUCTION_NAME = "Production"


class SensorConfig:
    """Data structure holding sensor configuration."""

    def __init__(self, name, sensor_type):
        """Sensor name and type to pass to API."""
        self.name = name
        self.sensor_type = sensor_type


# Sensor types/ranges
SENSOR_TYPES = {
    "active": SensorConfig(ACTIVE_NAME, ACTIVE_TYPE),
    "daily": SensorConfig("Daily", "DAY"),
    "weekly": SensorConfig("Weekly", "WEEK"),
    "monthly": SensorConfig("Monthly", "MONTH"),
    "yearly": SensorConfig("Yearly", "YEAR"),
}

# Production/consumption variants
SENSOR_VARIANTS = [PRODUCTION_NAME.lower(), CONSUMPTION_NAME.lower()]


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Sense sensor."""
    data = hass.data[DOMAIN][config_entry.entry_id][SENSE_DATA]

    @Throttle(MIN_TIME_BETWEEN_DAILY_UPDATES)
    async def update_trends():
        """Update the daily power usage."""
        await data.update_trend_data()

    async def update_active():
        """Update the active power usage."""
        await data.update_realtime()

    sense_monitor_id = data.sense_monitor_id

    devices = []
    for type_id in SENSOR_TYPES:
        typ = SENSOR_TYPES[type_id]
        for var in SENSOR_VARIANTS:
            name = typ.name
            sensor_type = typ.sensor_type
            is_production = var == PRODUCTION_NAME.lower()
            if sensor_type == ACTIVE_TYPE:
                update_call = update_active
            else:
                update_call = update_trends

            unique_id = f"{sense_monitor_id}-{type_id}-{var}".lower()
            devices.append(
                Sense(
                    data, name, sensor_type, is_production, update_call, var, unique_id
                )
            )

    async_add_entities(devices)


class Sense(Entity):
    """Implementation of a Sense energy sensor."""

    def __init__(
        self, data, name, sensor_type, is_production, update_call, sensor_id, unique_id
    ):
        """Initialize the Sense sensor."""
        name_type = PRODUCTION_NAME if is_production else CONSUMPTION_NAME
        self._name = f"{name} {name_type}"
        self._unique_id = unique_id
        self._available = False
        self._data = data
        self._sensor_type = sensor_type
        self.update_sensor = update_call
        self._is_production = is_production
        self._state = None

        if sensor_type == ACTIVE_TYPE:
            self._unit_of_measurement = POWER_WATT
        else:
            self._unit_of_measurement = ENERGY_KILO_WATT_HOUR

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def available(self):
        """Return the availability of the sensor."""
        return self._available

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return ICON

    @property
    def unique_id(self):
        """Return the unique id."""
        return self._unique_id

    async def async_update(self):
        """Get the latest data, update state."""

        try:
            await self.update_sensor()
        except SenseAPITimeoutException:
            _LOGGER.error("Timeout retrieving data")
            return

        if self._sensor_type == ACTIVE_TYPE:
            if self._is_production:
                self._state = round(self._data.active_solar_power)
            else:
                self._state = round(self._data.active_power)
        else:
            state = self._data.get_trend(self._sensor_type, self._is_production)
            self._state = round(state, 1)

        self._available = True
