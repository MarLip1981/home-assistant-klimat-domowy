"""Constants for Klimat Domowy."""

from datetime import timedelta

DOMAIN = "klimat_domowy"
PLATFORMS = ["sensor", "button"]
SCAN_INTERVAL = timedelta(minutes=5)

CONF_INDOOR_TEMPERATURE = "indoor_temperature"
CONF_INDOOR_HUMIDITY = "indoor_humidity"
CONF_INDOOR_TEMPERATURE_2 = "indoor_temperature_2"
CONF_INDOOR_HUMIDITY_2 = "indoor_humidity_2"
CONF_INDOOR_TEMPERATURE_3 = "indoor_temperature_3"
CONF_INDOOR_HUMIDITY_3 = "indoor_humidity_3"
CONF_OUTDOOR_TEMPERATURE = "outdoor_temperature"
CONF_OUTDOOR_HUMIDITY = "outdoor_humidity"
CONF_PM25 = "pm25"
CONF_PM10 = "pm10"
CONF_AQI = "aqi"
CONF_POLLEN_RISK = "pollen_risk"
CONF_POLLEN_RISK_HOURLY = "pollen_risk_hourly"
CONF_BOILER_STATE = "boiler_state"
CONF_RAIN = "rain"

DEFAULT_ENTITIES = {
    CONF_INDOOR_TEMPERATURE: "sensor.kuchnia_piec_ogrzewanie_current_temperature",
    CONF_INDOOR_HUMIDITY: "sensor.dom_zone_ogrzewanie_circuit_0_humidity",
    CONF_OUTDOOR_TEMPERATURE: "sensor.dom_outdoor_temperature",
    CONF_OUTDOOR_HUMIDITY: "sensor.rezydencja_relative_humidity",
    CONF_PM25: "sensor.openweathermap_pm2_5",
    CONF_PM10: "sensor.openweathermap_pm10",
    CONF_AQI: "sensor.openweathermap_indeks_jakosci_powietrza",
    CONF_POLLEN_RISK: "sensor.polleninformation_poland_50_9578_21_4163_allergy_risk",
    CONF_POLLEN_RISK_HOURLY: "sensor.polleninformation_poland_50_9578_21_4163_allergy_risk_hourly",
    CONF_BOILER_STATE: "sensor.dom_circuit_0_state",
    CONF_RAIN: "sensor.rezydencja_precipitation_last_hour",
}

CONF_PM25_LIMIT = "pm25_limit"
CONF_PM10_LIMIT = "pm10_limit"
DEFAULT_PM25_LIMIT = 15.0
DEFAULT_PM10_LIMIT = 45.0

CONF_NOTIFY_ENABLED = "notify_enabled"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFY_DELAY = "notify_delay_minutes"
DEFAULT_NOTIFY_ENABLED = True
DEFAULT_NOTIFY_SERVICE = "notify.cala_rodzina"
DEFAULT_NOTIFY_DELAY = 5
