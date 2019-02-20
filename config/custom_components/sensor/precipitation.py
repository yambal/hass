"""
Hass.io Yahoo 気象情報APIセンサー
https://developer.yahoo.co.jp/webapi/map/openlocalplatform/v1/weather.html
"""

import asyncio
import voluptuous as vol
import homeassistant.helpers.config_validation as confValue
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_LATITUDE, CONF_LONGITUDE, CONF_MONITORED_CONDITIONS, ATTR_ATTRIBUTION, CONF_NAME, CONF_API_KEY
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
DEFAULT_NAME = 'Yahoo Precipitation'
CONF_ATTRIBUTION = "(C) Yahoo Japan Corporation."

# データ取得間隔（秒）
FETCH_INTERVAL = 60 * 5;

# このコンポーネントでセンシングするセンサーのリストを定義
# スキーマ設定、エンティティ定義で参照される
SENSOR_TYPES = {
    'symbol': ['Graph', None],
    'rainfall': ['Rainfall', 'mm'],
    'forecast10': ['Forecast after 10 minutes', 'mm'],
    'forecast20': ['Forecast after 20 minutes', 'mm'],
    'forecast30': ['Forecast after 30 minutes', 'mm'],
    'forecast40': ['Forecast after 50 minutes', 'mm'],
    'forecast50': ['Forecast after 40 minutes', 'mm'],
    'forecast60': ['Forecast after 1 houre', 'mm'],
    'msg': ['Message', None],
    'digest': ['Digest', None],
    'update': ['Update', None],
    'rainy': ['Rainy', None],
}

# スキーマ設定
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_MONITORED_CONDITIONS, default=['rainfall']):
        vol.All(confValue.ensure_list, vol.Length(min=1), [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_LATITUDE): confValue.latitude,
    vol.Optional(CONF_LONGITUDE): confValue.longitude,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): confValue.string,
    vol.Optional(CONF_API_KEY): confValue.string,
})

_LOGGER = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# エンティティ定義
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    latitude = config.get(CONF_LATITUDE, hass.config.latitude)
    longitude = config.get(CONF_LONGITUDE, hass.config.longitude)
    name = config.get(CONF_NAME)
    appid = str(config.get(CONF_API_KEY))

    if appid is None or len(appid) == 0:
        _LOGGER.error("Wrong appid (api_key) supplied")
        return

    coordinates = str(longitude) + ',' + str(latitude)
    params = {
        'coordinates': coordinates,
        'output': 'json',
        'appid': appid,
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

    @property
    def entity_picture(self):
        if self.type != 'symbol':
            return None
        return self._state
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

        def try_again(err: str):
            # 再試行
            minutes = random.randint(3, 4)
            _LOGGER.error("Retrying in %i minutes: %s", minutes, err)
            async_call_later(self.hass, minutes*60, self.fetching_data)

        try:
            websession = async_get_clientsession(self.hass)
            with async_timeout.timeout(10, loop=self.hass.loop):
                resp = await websession.get(
                    self._url, params=self._urlparams)

            if resp.status != 200:
                _LOGGER.error("Retrying in %i minutes: %s", resp.url, resp.status)
                return

            jsonText = await resp.text()

        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            # エラー > 再試行
            try_again(err)
            return

        try:
            # JSON をパースする
            self.data = json.loads(jsonText)
        except (ExpatError, IndexError) as err:
            # パースエラー
            _LOGGER.error("JSON parse error:", jsonText)
            try_again(err)
            return

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

        r = [
            float(self.data['Feature'][0]['Property']['WeatherList']['Weather'][0]['Rainfall']),
            float(self.data['Feature'][0]['Property']['WeatherList']['Weather'][1]['Rainfall']),
            float(self.data['Feature'][0]['Property']['WeatherList']['Weather'][2]['Rainfall']),
            float(self.data['Feature'][0]['Property']['WeatherList']['Weather'][3]['Rainfall']),
            float(self.data['Feature'][0]['Property']['WeatherList']['Weather'][4]['Rainfall']),
            float(self.data['Feature'][0]['Property']['WeatherList']['Weather'][5]['Rainfall']),
            float(self.data['Feature'][0]['Property']['WeatherList']['Weather'][6]['Rainfall']),
        ]

        dateString = str(self.data['Feature'][0]['Property']['WeatherList']['Weather'][0]['Date']).strip()
        rainfallDict = {
            'rainfall': [r[0],'0分'],
            'forecast10': [r[1],'10分'],
            'forecast20': [r[2],'20分'],
            'forecast30': [r[3],'30分'],
            'forecast40': [r[4],'40分'],
            'forecast50': [r[5],'50分'],
            'forecast60': [r[6],'1時間'],
            'msg': [str(self.data['Feature'][0]['Name'])],
            'update': ['{}年{}月{}日{}時{}分'.format(dateString[0:4], dateString[4:6], dateString[6:8], dateString[8:10], dateString[10:12])],
            'symbol': ['https://image-charts.com/chart?chs=100x100&cht=bvg&chd=t:{}|{}|{}|{}|{}|{}|{}'.format(r[0],r[1],r[2],r[3],r[4],r[5],r[6])],
            'rainy': r[0] > 0,
        }

        # センサーごとに更新データをupdateStateTasksに詰める
        updateStateTasks = []
        for checkEntity in self.entities:
            newState = None

            if checkEntity.type in rainfallDict.keys():
                newState = rainfallDict[checkEntity.type][0]

            else:
                if checkEntity.type == 'digest':
                    if rainfallDict['rainfall'][0] == 0:
                        newState = "一時間以内に雨が降る予報はありません"
                        for idx in ['forecast60', 'forecast50', 'forecast40', 'forecast30', 'forecast20', 'forecast10']:
                            val = rainfallDict[idx]
                            if val[0] != 0:
                                newState = '{}前後で{}mmの雨が{}可能性があります'.format(val[1], val[0], '降る')

                    elif rainfallDict['rainfall'][0] != 0:
                        newState = '雨が降っています。一時間以内に止む予報はありません'
                        for idx in ['forecast60', 'forecast50', 'forecast40', 'forecast30', 'forecast20', 'forecast10']:
                            val = rainfallDict[idx]
                            if val[0] == 0:
                                newState = '{}前後で雨が止む可能性があります'.format(val[1])

            # 値に変化があれば更新タスクに追加
            if newState != checkEntity._state:
                checkEntity._state = newState
                updateStateTasks.append(checkEntity.async_update_ha_state())

        # updateStateTasks があれば更新を発火
        if updateStateTasks:
            await asyncio.wait(updateStateTasks, loop=self.hass.loop)
