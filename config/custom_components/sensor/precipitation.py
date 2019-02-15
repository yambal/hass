"""
定期的に非同期でデータをPULLするセンサー
参照
https://github.com/home-assistant/home-assistant/blob/master/homeassistant/components/sensor/yr.py
"""

import asyncio
import voluptuous as vol
import homeassistant.helpers.config_validation as confValue
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_LATITUDE, CONF_LONGITUDE, CONF_MONITORED_CONDITIONS, ATTR_ATTRIBUTION, CONF_NAME
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import (async_track_utc_time_change, async_call_later)

from homeassistant.helpers.aiohttp_client import async_get_clientsession

import logging
import async_timeout
import aiohttp
import random

# ------------------------------------------------------------------------------
# 設定
DEFAULT_NAME = 'Precipitation'
CONF_ATTRIBUTION = "開発ツール > Status などに表示される帰属"

# データ取得間隔（秒）
FETCH_INTERVAL = 60;

# このコンポーネントでセンシングするセンサーのリストを定義
# スキーマ設定、エンティティ定義で参照される
SENSOR_TYPES = {
    'rainfall': ['降水量', 'mm'],
    'msg': ['String', None],
}

# スキーマ設定
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_MONITORED_CONDITIONS, default=['rainfall']):
        vol.All(confValue.ensure_list, vol.Length(min=1), [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_LATITUDE): confValue.latitude,
    vol.Optional(CONF_LONGITUDE): confValue.longitude,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): confValue.string,
})

_LOGGER = logging.getLogger(__name__)



# ------------------------------------------------------------------------------
# エンティティ定義
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    latitude = config.get(CONF_LATITUDE, hass.config.latitude)
    longitude = config.get(CONF_LONGITUDE, hass.config.longitude)
    name = config.get(CONF_NAME)

    coordinates = str(longitude) + ',' + str(latitude)
    params = {
        'coordinates': coordinates,
        'output': 'json',
        'appid': 'm3nJD.Wxg67zvMjsW9l51cG95DM_C3lEyl.QSfDOW7UpokwjvpvpILWYtoTWBJwXEhx1QQ--',
    }

    # [monitored_conditions](正規化済み)のリスト毎にセンサーを生成
    # エンティティリスト entities に詰める
    entities = []
    for sensor_type in config[CONF_MONITORED_CONDITIONS]:
        entities.append(mySensorEntities(name, sensor_type))

    # 非同期エンティティリストとして登録
    async_add_entities(entities)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # データ取得Classを作成
    dataFetcher = myDataFetcher(hass, params, entities)

    # 時間がパターンと一致した場合に起動する同期リスナーを追加します。
    # （必要か？）
    # http://dev-docs.home-assistant.io/en/master/api/helpers.html
    async_track_utc_time_change(hass, dataFetcher.updating_devices, second=0)

    # 最初の取得と同期、ループの開始
    await dataFetcher.fetching_data()

# ------------------------------------------------------------------------------
# エンティティ定義
# ほぼ定型？
class mySensorEntities(Entity):
    def __init__(self, name, sensor_type):
      self.client_name = name
      self._state = None
      self.type = sensor_type
      self._name = SENSOR_TYPES[sensor_type][0]
      self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]

    @property
    def name(self):
        return '{} {}'.format(self.client_name, self._name)

    @property
    def state(self):
        return self._state

    @property
    def should_poll(self):
        return False

    @property
    def device_state_attributes(self):
        return {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION,
        }

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

# ------------------------------------------------------------------------------
# データ取得Class
class myDataFetcher:
    def __init__(self, hass, params, entities):
        self.data = {}
        self.hass = hass
        self.entities = entities
        self._url = 'https://map.yahooapis.jp/weather/V1/place'
        self._urlparams = params

    # データを取得し、センサーデータを更新、ループする
    async def fetching_data(self, *_):
        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        import json


        try:
            websession = async_get_clientsession(self.hass)
            with async_timeout.timeout(10, loop=self.hass.loop):
                resp = await websession.get(
                    self._url, params=self._urlparams)

            if resp.status != 200:
                _LOGGER.error("Retrying in %i minutes: %s", resp.url, resp.status)
                return

            text = await resp.text()


        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Retrying in %i minutes: %s", minutes, err)
            return

        _LOGGER.error(text)
        jsonDict = json.loads(text)
        #_LOGGER.error('json_dict:{}'.format(type(jsonDict)))
        #_LOGGER.error(jsonDict['Feature'][0]['Id'])
        #_LOGGER.error(jsonDict['Feature'][0]['Name'])
        _LOGGER.error(jsonDict['Feature'][0]['Property']['WeatherList']['Weather'][0]['Type'])
        _LOGGER.error(jsonDict['Feature'][0]['Property']['WeatherList']['Weather'][0]['Date'])

        # 応答名
        responseName = str(jsonDict['Feature'][0]['Name'])
        # 降水量
        rainfall = jsonDict['Feature'][0]['Property']['WeatherList']['Weather'][0]['Rainfall']

        self.data = {
            'rainfall_raw': rainfall,
            'msg_raw': responseName,
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
            if checkEntity.type == 'rainfall':
                newState = float(self.data['rainfall_raw'])

            elif checkEntity.type == 'msg':
                newState = str(self.data['msg_raw'])

            # 値に変化があれば更新タスクに追加
            if newState != checkEntity._state:
                checkEntity._state = newState
                updateStateTasks.append(checkEntity.async_update_ha_state())

        # updateStateTasks があれば更新を発火
        if updateStateTasks:
            await asyncio.wait(updateStateTasks, loop=self.hass.loop)
