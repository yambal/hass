
import random
import asyncio
import logging
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_LATITUDE, CONF_LONGITUDE, CONF_ELEVATION, CONF_MONITORED_CONDITIONS, ATTR_ATTRIBUTION, CONF_NAME
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import (async_track_utc_time_change, async_call_later)

DEFAULT_NAME = 'JR West'
CONF_ATTRIBUTION = "Weather forecast from met.no, delivered by the Norwegian Meteorological Institute."

_LOGGER = logging.getLogger(DEFAULT_NAME)

"""このコンポーネントでセンシングするセンサーのリストを定義"""
SENSOR_TYPES = {
    'pressure': ['Pressure', 'hPa'],
    'num': ['Number', 'num'],
}


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_MONITORED_CONDITIONS, default=['pressure']):
        vol.All(cv.ensure_list, vol.Length(min=1), [vol.In(SENSOR_TYPES)]),
})

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    dev = []

    """
    [monitored_conditions](正規化済み)のリスト毎にセンサーを生成
    エンティティリスト dev に詰める
    非同期エンティティとして登録
    """
    for sensor_type in config[CONF_MONITORED_CONDITIONS]:
        dev.append(JRWestSensor(DEFAULT_NAME, sensor_type))

    async_add_entities(dev)

    jrwData = JRWestData(hass, dev)

    """時間がパターンと一致した場合に起動する同期リスナーを追加します。"""
    async_track_utc_time_change(hass, jrwData.updating_devices, second=0)

    """最初の取得と同期、ループの開始"""
    await jrwData.fetching_data()


class JRWestSensor(Entity):

    def __init__(self, name, sensor_type):
      _LOGGER.info('JRWestSensor init')
      self.client_name = name
      self._state = None
      self.type = sensor_type
      self._name = SENSOR_TYPES[sensor_type][0]
      self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]

    @property
    def name(self):
        """Return the name of the sensor."""
        return '{} {}'.format(self.client_name, self._name)

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION,
        }

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement



"""Get the latest data and updates the states."""
class JRWestData:

    def __init__(self, hass, devices):
        self.data = {}
        self.hass = hass
        self.devices = devices

    """データを取得する"""
    async def fetching_data(self, *_):

        self.data = {
            'hoge': 36
        }

        await self.updating_devices()
        async_call_later(self.hass, 60*60, self.fetching_data)

    """self.dataから現在のデータを見つけます。"""
    async def updating_devices(self, *_):
        if not self.data:
            return

        tasks = []
        for dev in self.devices:
            new_state = random.randint(0, 50)

            if new_state != dev._state:
                dev._state = new_state
                tasks.append(dev.async_update_ha_state())

        if tasks:
            await asyncio.wait(tasks, loop=self.hass.loop)
