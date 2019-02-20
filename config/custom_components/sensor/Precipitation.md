# Hass.io Yahoo 気象情報APIセンサー

## ソースコード
[precipitation.py](https://github.com/yambal/hass/blob/master/config/custom_components/sensor/precipitation.py)

蒸気コードを`/config/custom_components/sensor/precipitation.py`として配置してください

## configuration.yaml
```configuration.yaml
sensor:
- platform: precipitation
  api_key:[YOUR_APPID]
  monitored_conditions:
    - rainfall
    - forecast10
    - forecast20
    - forecast30
    - forecast40
    - forecast50
    - forecast60
    - symbol
    - digest
    - msg
    - update
```
- api_key : [Yahoo! JAPAN デベロッパーネットワーク](https://developer.yahoo.co.jp/)で取得した appid
- rainfall : 現在の雨量
- forecast10 : 10分後の雨量予測
- ...
- forecast60 : 1時間後の雨量予測
- symbol : Badge に指定する画像（グラフ）
- digest : 概要文
  - 一時間以内に雨が降る予報はありません...など
- msg : メッセージ
  - 2019年02月20日 23時25分から60分間の天気情報...など
- update : 予報の最終更新日時
  - 2019年02月20日23時25分...など
  - （情報の取得時刻ではありません）
