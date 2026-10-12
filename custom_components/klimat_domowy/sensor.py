"""Sensors and recommendation engine for Klimat Domowy."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    CONF_AQI,
    CONF_BOILER_STATE,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_PM10,
    CONF_PM10_LIMIT,
    CONF_PM25,
    CONF_PM25_LIMIT,
    CONF_POLLEN_RISK,
    CONF_POLLEN_RISK_HOURLY,
    CONF_RAIN,
    DOMAIN,
    SCAN_INTERVAL,
)


@dataclass(frozen=True, kw_only=True)
class KlimatSensorDescription(SensorEntityDescription):
    """Describe an output sensor."""

    value_key: str


SENSORS: tuple[KlimatSensorDescription, ...] = (
    KlimatSensorDescription(
        key="recommendation",
        value_key="recommendation",
        name="Zalecenie wietrzenia",
        icon="mdi:window-open-variant",
    ),
    KlimatSensorDescription(
        key="air_quality",
        value_key="air_quality",
        name="Ocena powietrza zewnętrznego",
        icon="mdi:air-filter",
    ),
    KlimatSensorDescription(
        key="allergy_risk",
        value_key="allergy_risk",
        name="Ryzyko alergiczne",
        icon="mdi:flower-pollen",
    ),
    KlimatSensorDescription(
        key="indoor_temperature",
        value_key="indoor_temperature",
        name="Temperatura wewnętrzna",
        native_unit_of_measurement="°C",
        device_class="temperature",
        state_class="measurement",
        icon="mdi:home-thermometer",
    ),
    KlimatSensorDescription(
        key="indoor_humidity",
        value_key="indoor_humidity",
        name="Wilgotność wewnętrzna",
        native_unit_of_measurement="%",
        device_class="humidity",
        state_class="measurement",
        icon="mdi:water-percent",
    ),
    KlimatSensorDescription(
        key="outdoor_temperature",
        value_key="outdoor_temperature",
        name="Temperatura zewnętrzna",
        native_unit_of_measurement="°C",
        device_class="temperature",
        state_class="measurement",
        icon="mdi:thermometer",
    ),
    KlimatSensorDescription(
        key="boiler_state",
        value_key="boiler_state",
        name="Stan obiegu grzewczego",
        icon="mdi:fire",
    ),
)


def _number(value: Any) -> float | None:
    """Parse a numeric sensor state safely."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and abs(parsed) != float("inf") else None


def _text(value: Any) -> str:
    """Normalize text states."""
    if value is None:
        return ""
    return str(value).strip().lower().replace("_", " ").replace("-", " ")


def _absolute_humidity(temp_c: float | None, relative_humidity: float | None) -> float | None:
    """Calculate absolute humidity in g/m³ from temperature and relative humidity."""
    if temp_c is None or relative_humidity is None:
        return None
    if not 0 <= relative_humidity <= 100 or temp_c <= -243.5:
        return None
    vapor_pressure = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))
    return 216.74 * vapor_pressure * (relative_humidity / 100) / (273.15 + temp_c)


def _pollen_is_high(value: Any) -> bool:
    """Recognize common text and numeric pollen risk levels."""
    text = _text(value)
    if not text or text in {"unknown", "unavailable", "none", "n/a"}:
        return False
    if any(word in text for word in ("very high", "extreme", "severe", "bardzo wysok", "wysok")):
        return True
    # Some integrations expose a 0-5 ordinal risk scale. Only 4-5 are treated
    # as high here; verify the actual integration's scale before relying on it.
    numeric = _number(text)
    return numeric is not None and numeric >= 4


def _pollen_is_present(value: Any) -> bool:
    """Recognize a non-zero numeric pollen index where supported."""
    text = _text(value)
    if not text or text in {"unknown", "unavailable", "none", "n/a"}:
        return False
    numeric = _number(text)
    if numeric is not None:
        return numeric > 0
    return any(word in text for word in ("low", "moderate", "medium", "high", "very high", "niski", "umiark", "wysok"))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up output sensors."""
    options = dict(entry.data)
    options.update(entry.options)

    async def async_update_data() -> dict[str, Any]:
        """Read source entities and produce one shared recommendation."""
        def state_for(key: str) -> str | None:
            entity_id = options.get(key)
            if not entity_id:
                return None
            state = hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                return None
            return state.state

        temp_in = _number(state_for(CONF_INDOOR_TEMPERATURE))
        hum_in = _number(state_for(CONF_INDOOR_HUMIDITY))
        temp_out = _number(state_for(CONF_OUTDOOR_TEMPERATURE))
        hum_out = _number(state_for(CONF_OUTDOOR_HUMIDITY))
        abs_humidity_in = _absolute_humidity(temp_in, hum_in)
        abs_humidity_out = _absolute_humidity(temp_out, hum_out)
        pm25 = _number(state_for(CONF_PM25))
        pm10 = _number(state_for(CONF_PM10))
        aqi = _number(state_for(CONF_AQI))
        pollen_values = [
            state_for(CONF_POLLEN_RISK),
            state_for(CONF_POLLEN_RISK_HOURLY),
        ]
        boiler = state_for(CONF_BOILER_STATE) or "BRAK DANYCH"
        rain = _number(state_for(CONF_RAIN))
        pm25_limit = _number(options.get(CONF_PM25_LIMIT)) or 15.0
        pm10_limit = _number(options.get(CONF_PM10_LIMIT)) or 45.0

        pollution_known = any(value is not None for value in (pm25, pm10, aqi))
        poor_air_reasons: list[str] = []
        if pm25 is not None and pm25 > pm25_limit:
            poor_air_reasons.append(f"PM2.5 {pm25:g}")
        if pm10 is not None and pm10 > pm10_limit:
            poor_air_reasons.append(f"PM10 {pm10:g}")
        # OpenWeatherMap air pollution index is commonly 1 (best) to 5 (worst).
        if aqi is not None and aqi >= 3:
            poor_air_reasons.append(f"indeks jakości powietrza {aqi:g}")
        poor_air = bool(poor_air_reasons)

        pollen_known = any(
            value is not None
            and _text(value) not in {"", "unknown", "unavailable", "none", "n/a"}
            for value in pollen_values
        )
        pollen_high = any(_pollen_is_high(value) for value in pollen_values)
        pollen_present = any(_pollen_is_present(value) for value in pollen_values)

        if not pollution_known:
            air_quality = "Brak danych"
        elif poor_air:
            air_quality = "Podwyższone zanieczyszczenia"
        else:
            air_quality = "Brak przekroczenia ustawionych progów"

        if not pollen_known:
            allergy_risk = "Brak danych"
        elif pollen_high:
            allergy_risk = "Wysokie"
        elif pollen_present:
            allergy_risk = "Pyłki wykryte — poziom do weryfikacji"
        else:
            allergy_risk = "Niskie według dostępnych danych"

        data_incomplete = temp_in is None or hum_in is None or temp_out is None
        if data_incomplete:
            recommendation = "Sprawdź czujniki — brak pełnych danych"
            reason = "Brakuje temperatury wewnętrznej/zewnętrznej lub wilgotności wewnętrznej."
        elif poor_air:
            recommendation = "Ogranicz wietrzenie — zanieczyszczenia"
            reason = "Podwyższone wskazania: " + ", ".join(poor_air_reasons) + ". Wietrz niezbędnie i krótko; rozważ filtrację."
        elif pollen_high:
            recommendation = "Wietrz krótko — wysokie ryzyko pyłków"
            reason = "Dane o pyłkach wskazują wysokie ryzyko alergiczne."
        elif hum_in >= 70:
            recommendation = "Pilnie ogranicz wilgoć"
            if abs_humidity_in is not None and abs_humidity_out is not None and abs_humidity_out <= abs_humidity_in - 1.0:
                reason = (
                    "Wilgotność wewnętrzna jest bardzo wysoka, a powietrze zewnętrzne ma "
                    "wyraźnie mniej wilgoci bezwzględnej. Jeśli jakość powietrza i pyłki "
                    "na to pozwalają, krótko przewietrz; użyj też wyciągu i sprawdź źródła wilgoci."
                )
            else:
                reason = (
                    "Wilgotność wewnętrzna jest bardzo wysoka. Użyj sprawnego wyciągu "
                    "i sprawdź źródła wilgoci. Nie zakładaj, że samo otwarcie okna osuszy "
                    "dom — wilgotność bezwzględna na zewnątrz nie jest wyraźnie niższa "
                    "albo brakuje danych do porównania."
                )
        elif hum_in >= 60:
            recommendation = "Obserwuj wilgotność — rozważ krótkie wietrzenie"
            if abs_humidity_in is not None and abs_humidity_out is not None:
                if abs_humidity_out <= abs_humidity_in - 1.0:
                    reason = (
                        "Wilgotność wewnętrzna jest podwyższona, a powietrze zewnętrzne "
                        "jest wyraźnie suchsze w ujęciu bezwzględnym. Krótkie wietrzenie "
                        "może pomóc, jeśli jakość powietrza i ryzyko pyłków są odpowiednie."
                    )
                else:
                    reason = (
                        "Wilgotność wewnętrzna jest podwyższona, ale powietrze zewnętrzne "
                        "nie jest wyraźnie suchsze. Wietrz z uwzględnieniem jakości powietrza "
                        "i korzystaj z wyciągu przy źródłach wilgoci."
                    )
            else:
                reason = (
                    "Wilgotność wewnętrzna jest podwyższona, ale brakuje danych do "
                    "porównania ilości wilgoci w powietrzu wewnątrz i na zewnątrz. "
                    "Nie zakładaj, że samo otwarcie okna osuszy dom."
                )
        elif temp_out < 10:
            recommendation = "Wietrz krótko i intensywnie"
            reason = "Chłodna pogoda: zwykle wystarczy około 3–5 minut intensywnego wietrzenia."
        elif temp_out < 18:
            recommendation = "Można krótko przewietrzyć"
            reason = "Umiarkowana temperatura zewnętrzna sprzyja krótkiej wymianie powietrza, jeśli nie ma innych przeciwwskazań."
        elif temp_out < temp_in:
            recommendation = "Można chłodzić dom"
            reason = "Na zewnątrz jest chłodniej niż wewnątrz; korzystaj z tego, jeśli potrzebujesz obniżyć temperaturę."
        else:
            recommendation = "Ogranicz wietrzenie dla chłodzenia"
            reason = "Na zewnątrz nie jest chłodniej niż w domu. Wietrz nadal, gdy wymaga tego jakość powietrza wewnętrznego."

        if not pollution_known:
            reason += " Brak odczytów zanieczyszczeń nie oznacza, że powietrze jest czyste."
        if not pollen_known:
            reason += " Brak danych o pyłkach nie oznacza braku alergenów."
        if boiler.upper() == "HEATING":
            reason += " Obieg grzewczy pracuje — unikaj długiego wychładzania; nie jest to bezwzględny zakaz wietrzenia."
        elif boiler.upper() not in {"STANDBY", "BRAK DANYCH"}:
            reason += f" Stan obiegu grzewczego: {boiler}."
        if rain is not None and rain > 0:
            reason += " Odnotowano opady — zabezpiecz okna przed deszczem."

        return {
            "recommendation": recommendation,
            "air_quality": air_quality,
            "allergy_risk": allergy_risk,
            "indoor_temperature": temp_in,
            "indoor_humidity": hum_in,
            "outdoor_temperature": temp_out,
            "boiler_state": boiler,
            "attributes": {
                "reason": reason,
                "indoor_temperature": temp_in,
                "indoor_humidity": hum_in,
                "outdoor_temperature": temp_out,
                "outdoor_humidity": hum_out,
                "indoor_absolute_humidity_g_m3": round(abs_humidity_in, 2) if abs_humidity_in is not None else None,
                "outdoor_absolute_humidity_g_m3": round(abs_humidity_out, 2) if abs_humidity_out is not None else None,
                "absolute_humidity_difference_g_m3": round(abs_humidity_in - abs_humidity_out, 2) if abs_humidity_in is not None and abs_humidity_out is not None else None,
                "pm2_5": pm25,
                "pm10": pm10,
                "air_quality_index": aqi,
                "pollen_risk": pollen_values[0],
                "pollen_risk_hourly": pollen_values[1],
                "boiler_state": boiler,
                "rain_last_hour": rain,
                "pollution_data_available": pollution_known,
                "pollen_data_available": pollen_known,
                "pollution_threshold_pm2_5": pm25_limit,
                "pollution_threshold_pm10": pm10_limit,
                "poor_air_reasons": poor_air_reasons,
                "advice_is_medical": False,
            },
        }

    coordinator = DataUpdateCoordinator(
        hass,
        logger=logging.getLogger(__name__),
        name="Klimat Domowy",
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    source_entity_ids = {
        options.get(key)
        for key in (
            CONF_INDOOR_TEMPERATURE,
            CONF_INDOOR_HUMIDITY,
            CONF_OUTDOOR_TEMPERATURE,
            CONF_OUTDOOR_HUMIDITY,
            CONF_PM25,
            CONF_PM10,
            CONF_AQI,
            CONF_POLLEN_RISK,
            CONF_POLLEN_RISK_HOURLY,
            CONF_BOILER_STATE,
            CONF_RAIN,
        )
        if options.get(key)
    }

    @callback
    def _source_changed(event) -> None:
        """Refresh promptly when one of the selected source sensors changes."""
        coordinator.async_request_refresh()

    if source_entity_ids:
        entry.async_on_unload(
            async_track_state_change_event(
                hass, list(source_entity_ids), _source_changed
            )
        )

    async_add_entities(
        KlimatDomowySensor(coordinator, entry, description)
        for description in SENSORS
    )


class KlimatDomowySensor(CoordinatorEntity, SensorEntity):
    """Expose a value from the shared recommendation coordinator."""

    entity_description: KlimatSensorDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        description: KlimatSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Klimat Domowy",
            "manufacturer": "MarLip1981",
            "model": "Silnik zaleceń jakości powietrza",
            "configuration_url": "https://github.com/MarLip1981/home-assistant-klimat-domowy",
        }

    @property
    def native_value(self):
        """Return the current sensor value."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.value_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the same context to cards and automations."""
        if not self.coordinator.data:
            return {}
        return dict(self.coordinator.data.get("attributes", {}))
