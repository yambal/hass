"""
https://github.com/home-assistant/home-assistant/blob/master/homeassistant/components/sensor/yr.py
"""

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

DEFAULT_NAME = 'Sensor Base'
CONF_ATTRIBUTION = "開発ツール > Status などに表示される帰属"

# _LOGGER = logging.getLogger(DEFAULT_NAME)

# データ取得間隔（秒）
FETCH_INTERVAL = 60;

# このコンポーネントでセンシングするセンサーのリストを定義
# スキーマ設定、エンティティ定義で参照される
SENSOR_TYPES = {
    'num': ['Number', 'num'],
    'msg': ['String', None],
}

# スキーマ設定
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_MONITORED_CONDITIONS, default=['a']):
        vol.All(cv.ensure_list, vol.Length(min=1), [vol.In(SENSOR_TYPES)]),
})

# ------------------------------------------------------------------------------
# エンティティ定義
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):

    # [monitored_conditions](正規化済み)のリスト毎にセンサーを生成
    # エンティティリスト dev に詰める
    entities = []
    for sensor_type in config[CONF_MONITORED_CONDITIONS]:
        entities.append(mySensorEntities(DEFAULT_NAME, sensor_type))

    # 非同期エンティティリストとして登録
    async_add_entities(entities)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # データ取得Classを作成
    dataFetcher = myDataFetcher(hass, entities)

    # 時間がパターンと一致した場合に起動する同期リスナーを追加します。
    # （必要か？）
    # http://dev-docs.home-assistant.io/en/master/api/helpers.html
    async_track_utc_time_change(hass, dataFetcher.updating_devices, second=0)

    # 最初の取得と同期、ループの開始
    await dataFetcher.fetching_data()

# ------------------------------------------------------------------------------
# エンティティ定義
class mySensorEntities(Entity):
    def __init__(self, name, sensor_type):
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

# ------------------------------------------------------------------------------
# データ取得Class
class myDataFetcher:
    def __init__(self, hass, entities):
        self.data = {}
        self.hass = hass
        self.entities = entities

    # データを取得し、センサーデータを更新、ループする
    async def fetching_data(self, *_):
        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        # データを取得して self.data に詰める
        # この時点では生データで良い
        # 取得データとして例示としてテキトーなデータを生成
        numA = random.randint(0, 50)
        self.data = {
            'num_raw': int(numA),
            'msg_raw': "Message " + str(numA),
        }
        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        # 後処理
        # センサークラスに更新を発火
        await self.updating_devices()

        # 指定秒後に再実行
        async_call_later(self.hass, FETCH_INTERVAL, self.fetching_data)

    # センサーデータを更新する
    async def updating_devices(self, *_):
        # データが無いなら何もしない
        if not self.data:
            return

        # センサーごとに更新データをupdateStateTasksに詰める
        updateStateTasks = []
        for checkEntity in self.entities:
            newState = None
            if checkEntity.type == 'num':
                newState = int(self.data['num_raw'])

            elif checkEntity.type == 'msg':
                newState = str(self.data['msg_raw'])

            # 値に変化があれば更新タスクに追加
            if newState != checkEntity._state:
                checkEntity._state = newState
                updateStateTasks.append(checkEntity.async_update_ha_state())

        # updateStateTasks があれば更新を発火
        if updateStateTasks:
            await asyncio.wait(updateStateTasks, loop=self.hass.loop)
