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
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .pollen import (
    is_high as _pollen_is_high,
    is_known as _pollen_is_known,
    is_low as _pollen_is_low,
    is_none_detected as _pollen_is_none_detected,
    is_present as _pollen_is_present,
    number as _number,
)

from .const import (
    CONF_AQI,
    CONF_BOILER_STATE,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_HUMIDITY_2,
    CONF_INDOOR_HUMIDITY_3,
    CONF_INDOOR_TEMPERATURE,
    CONF_INDOOR_TEMPERATURE_2,
    CONF_INDOOR_TEMPERATURE_3,
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


def _absolute_humidity(temp_c: float | None, relative_humidity: float | None) -> float | None:
    """Calculate absolute humidity in g/m³ from temperature and relative humidity."""
    if temp_c is None or relative_humidity is None:
        return None
    if not 0 <= relative_humidity <= 100 or temp_c <= -243.5:
        return None
    vapor_pressure = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))
    return 216.74 * vapor_pressure * (relative_humidity / 100) / (273.15 + temp_c)


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

        indoor_rooms = [
            {
                "name": "Pomieszczenie 1",
                "temperature": _number(state_for(CONF_INDOOR_TEMPERATURE)),
                "humidity": _number(state_for(CONF_INDOOR_HUMIDITY)),
            },
            {
                "name": "Pomieszczenie 2",
                "temperature": _number(state_for(CONF_INDOOR_TEMPERATURE_2)),
                "humidity": _number(state_for(CONF_INDOOR_HUMIDITY_2)),
            },
            {
                "name": "Pomieszczenie 3",
                "temperature": _number(state_for(CONF_INDOOR_TEMPERATURE_3)),
                "humidity": _number(state_for(CONF_INDOOR_HUMIDITY_3)),
            },
        ]
        valid_temperatures = [room["temperature"] for room in indoor_rooms if room["temperature"] is not None]
        valid_humidities = [room["humidity"] for room in indoor_rooms if room["humidity"] is not None]
        temp_in = sum(valid_temperatures) / len(valid_temperatures) if valid_temperatures else None
        temp_in_max = max(valid_temperatures) if valid_temperatures else None
        hum_in = max(valid_humidities) if valid_humidities else None
        temp_out = _number(state_for(CONF_OUTDOOR_TEMPERATURE))
        hum_out = _number(state_for(CONF_OUTDOOR_HUMIDITY))
        indoor_absolute_humidities = [
            _absolute_humidity(room["temperature"], room["humidity"])
            for room in indoor_rooms
            if room["temperature"] is not None and room["humidity"] is not None
        ]
        indoor_absolute_humidities = [value for value in indoor_absolute_humidities if value is not None]
        abs_humidity_in = max(indoor_absolute_humidities) if indoor_absolute_humidities else None
        abs_humidity_out = _absolute_humidity(temp_out, hum_out)
        pm25 = _number(state_for(CONF_PM25))
        pm10 = _number(state_for(CONF_PM10))
        # Prefer the user's local Ostrowiec air-quality index when it exposes a
        # recognized Polish category (or a 1–6 category number). If unavailable
        # or unrecognized, retain the configured AQI sensor as a fallback.
        local_aqi_entity = "sensor.ostrowiec_swietokrzyski_ul_polna_indeks_jakosci_powietrza"
        local_aqi_raw = state_for(local_aqi_entity)
        local_aqi_text = str(local_aqi_raw or "").strip().lower()
        local_aqi_text = (
            local_aqi_text.replace("ł", "l")
            .replace("ą", "a")
            .replace("ę", "e")
            .replace("ó", "o")
            .replace("ś", "s")
            .replace("ć", "c")
            .replace("ż", "z")
            .replace("ź", "z")
            .replace("ń", "n")
        )
        local_aqi_categories = (
            ("bardzo zly", "Bardzo zła", 6),
            ("zly", "Zła", 5),
            ("dostateczny", "Dostateczna", 4),
            ("umiarkowany", "Umiarkowana", 3),
            ("dobry", "Dobra", 2),
            ("bardzo dobry", "Bardzo dobra", 1),
        )
        local_aqi_label = None
        local_aqi_rank = None
        for category, label, rank in local_aqi_categories:
            if category in local_aqi_text:
                local_aqi_label = label
                local_aqi_rank = rank
                break
        if local_aqi_rank is None:
            local_aqi_number = _number(local_aqi_raw)
            if local_aqi_number is not None and local_aqi_number.is_integer() and 1 <= local_aqi_number <= 6:
                local_aqi_rank = int(local_aqi_number)
                local_aqi_label = {
                    1: "Bardzo dobra",
                    2: "Dobra",
                    3: "Umiarkowana",
                    4: "Dostateczna",
                    5: "Zła",
                    6: "Bardzo zła",
                }[local_aqi_rank]
        local_aqi_used = local_aqi_rank is not None
        aqi = float(local_aqi_rank) if local_aqi_used else _number(state_for(CONF_AQI))
        pollen_values = [
            state_for(CONF_POLLEN_RISK),
            state_for(CONF_POLLEN_RISK_HOURLY),
        ]
        boiler_raw = state_for(CONF_BOILER_STATE) or "BRAK DANYCH"
        boiler_labels = {
            "HEATING": "Grzeje",
            "STANDBY": "Gotowy — nie grzeje",
            "IDLE": "Nie grzeje",
            "OFF": "Wyłączony",
            "OFFLINE": "Niedostępny",
            "UNAVAILABLE": "Niedostępny",
            "UNKNOWN": "Brak danych",
            "BRAK DANYCH": "Brak danych",
        }
        boiler = boiler_labels.get(boiler_raw.strip().upper(), boiler_raw)
        rain = _number(state_for(CONF_RAIN))
        pm25_limit = _number(options.get(CONF_PM25_LIMIT)) or 15.0
        pm10_limit = _number(options.get(CONF_PM10_LIMIT)) or 45.0

        pollution_known = any(value is not None for value in (pm25, pm10, aqi))
        poor_air_reasons: list[str] = []
        if pm25 is not None and pm25 > pm25_limit:
            poor_air_reasons.append(f"PM2.5 {pm25:g}")
        if pm10 is not None and pm10 > pm10_limit:
            poor_air_reasons.append(f"PM10 {pm10:g}")
        # The local Ostrowiec index has six Polish categories; warn from
        # "dostateczna" upward. Keep the configured OpenWeatherMap 1–5 scale
        # unchanged when the local source is unavailable.
        if local_aqi_used:
            if local_aqi_rank is not None and local_aqi_rank >= 4:
                poor_air_reasons.append(f"lokalny indeks jakości powietrza: {local_aqi_label}")
        elif aqi is not None and aqi >= 3:
            poor_air_reasons.append(f"indeks jakości powietrza {aqi:g}")
        poor_air = bool(poor_air_reasons)

        pollen_known = any(_pollen_is_known(value) for value in pollen_values)
        pollen_none_detected = any(_pollen_is_none_detected(value) for value in pollen_values)
        pollen_high = any(_pollen_is_high(value) for value in pollen_values)
        pollen_low = any(_pollen_is_low(value) for value in pollen_values)
        pollen_present = any(_pollen_is_present(value) for value in pollen_values)

        # OpenWeatherMap AQI is categorical: 1 is best, 5 is worst.
        # Show a human-readable Polish label instead of the raw numeric code.
        aqi_labels = {
            1: "Bardzo dobra",
            2: "Dobra",
            3: "Umiarkowana",
            4: "Zła",
            5: "Bardzo zła",
        }
        aqi_label = (
            local_aqi_label
            if local_aqi_used
            else aqi_labels.get(int(aqi)) if aqi is not None and aqi.is_integer() else None
        )
        pm_limit_exceeded = any(
            value is not None and value > limit
            for value, limit in ((pm25, pm25_limit), (pm10, pm10_limit))
        )
        if not pollution_known:
            air_quality = "Brak danych"
        elif pm_limit_exceeded:
            air_quality = "Niezadowalająca — przekroczony próg pyłów"
        elif aqi_label is not None:
            air_quality = aqi_label
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
        elif pollen_none_detected:
            allergy_risk = "Brak wykrytych pyłków"
        elif pollen_low:
            allergy_risk = "Niskie"
        else:
            allergy_risk = "Poziom ryzyka nieznany"

        data_incomplete = not valid_temperatures or not valid_humidities or temp_out is None
        # Calendar season is context only; measured conditions take priority.
        local_month = dt_util.now().month
        if local_month in (12, 1, 2):
            season = "zima"
        elif local_month in (3, 4, 5):
            season = "wiosna"
        elif local_month in (6, 7, 8):
            season = "lato"
        else:
            season = "jesień"

        # Give an explicit outdoor-air verdict. Never ask the user to decide whether
        # the air is clean; state exactly what the configured sensors can establish.
        if poor_air:
            outdoor_air_verdict = (
                f"Powietrze na zewnątrz: NIEKORZYSTNE — {', '.join(poor_air_reasons)} "
                f"(przekroczony próg ostrzegawczy)."
            )
        elif pollution_known:
            outdoor_air_verdict = (
                "Powietrze na zewnątrz: brak przekroczeń w dostępnych pomiarach "
                "(to nie jest gwarancja pełnej czystości powietrza)."
            )
        else:
            outdoor_air_verdict = (
                "Powietrze na zewnątrz: NIE MOŻNA OCENIĆ — brak aktualnych "
                "pomiarów zanieczyszczeń."
            )

        if pollen_high:
            outdoor_pollen_verdict = "Ryzyko pyłków: wysokie."
        elif pollen_present:
            outdoor_pollen_verdict = "Ryzyko pyłków: wykryto pyłki; zalecana ostrożność."
        elif pollen_low:
            outdoor_pollen_verdict = "Ryzyko pyłków: niskie według dostępnych danych."
        elif pollen_none_detected:
            outdoor_pollen_verdict = "Ryzyko pyłków: źródło nie wykrywa obecnie pyłków."
        else:
            outdoor_pollen_verdict = "Ryzyko pyłków: brak aktualnych danych."

        humidity_can_be_reduced = (
            abs_humidity_in is not None
            and abs_humidity_out is not None
            and abs_humidity_out <= abs_humidity_in - 1.0
        )
        outdoor_air_favorable = (
            pollution_known
            and not poor_air
            and pollen_known
            and not pollen_high
            and not pollen_present
        )
        if hum_in is not None and hum_in >= 70:
            recommendation = "Pilnie ogranicz wilgoć"
            if humidity_can_be_reduced and outdoor_air_favorable:
                reason = (
                    f"W domu wilgotność wynosi {hum_in:.0f}%. Powietrze na zewnątrz "
                    "ma wyraźnie niższą wilgoć bezwzględną, a dostępne pomiary nie "
                    "wskazują na podwyższone zanieczyszczenia ani istotne ryzyko pyłków. "
                    "Wietrz krótko i intensywnie, a także włącz wyciąg oraz usuń źródło wilgoci."
                )
            else:
                reason = (
                    f"W domu wilgotność wynosi {hum_in:.0f}% — to wysoki poziom. "
                    "Włącz wyciąg i sprawdź źródła wilgoci. Nie polegaj na długim wietrzeniu: "
                    + outdoor_air_verdict + " " + outdoor_pollen_verdict
                )
                if not humidity_can_be_reduced:
                    reason += (
                        " Na podstawie temperatury i wilgotności bezwzględnej nie ma "
                        "potwierdzenia, że powietrze z zewnątrz skutecznie osuszy dom."
                    )
        elif hum_in is not None and hum_in >= 60:
            recommendation = "Obserwuj wilgotność — oceń możliwość krótkiego wietrzenia"
            if humidity_can_be_reduced and outdoor_air_favorable:
                reason = (
                    f"W domu wilgotność wynosi {hum_in:.0f}%. Powietrze na zewnątrz "
                    "jest wyraźnie suchsze, a dostępne pomiary nie wskazują na "
                    "podwyższone zanieczyszczenia ani istotne ryzyko pyłków. "
                    "Krótkie, intensywne wietrzenie powinno pomóc; używaj wyciągu "
                    "przy gotowaniu i kąpieli."
                )
            else:
                reason = (
                    f"W domu wilgotność wynosi {hum_in:.0f}%. "
                    + outdoor_air_verdict + " " + outdoor_pollen_verdict
                )
                if not humidity_can_be_reduced:
                    reason += (
                        " Powietrze z zewnątrz nie jest obecnie wyraźnie suchsze "
                        "według dostępnych pomiarów, więc samo wietrzenie może nie obniżyć wilgotności."
                    )
                else:
                    reason += (
                        " Włącz wyciąg przy gotowaniu i kąpieli. Jeśli musisz wymienić "
                        "powietrze, zrób to krótko i intensywnie, zamiast długo uchylać okno."
                    )
        elif poor_air:
            recommendation = "Ogranicz wietrzenie — zanieczyszczenia"
            reason = f"Powietrze na zewnątrz przekracza ustawione progi: {', '.join(poor_air_reasons)}. Ogranicz wietrzenie; jeśli musisz wymienić powietrze, otwórz okna na krótko. Jeśli masz oczyszczacz, warto go włączyć."
            if pollen_high or pollen_present:
                reason += " Dodatkowo zwróć uwagę na pyłki — mogą nasilać objawy alergii."
        elif pollen_high:
            recommendation = "Wietrz krótko — wysokie ryzyko pyłków"
            reason = "W powietrzu może być dużo pyłków. Wietrz krótko i, jeśli możesz, wybierz porę z mniejszym ryzykiem."
        elif pollen_present:
            recommendation = "Wietrz krótko — pyłki wykryte"
            reason = "Wykryto pyłki. Otwieraj okna na krótko i obserwuj, czy pojawiają się objawy alergii."
        elif data_incomplete:
            recommendation = "Sprawdź czujniki — brak pełnych danych"
            reason = "Brakuje części odczytów, więc zalecenie może być niedokładne. Sprawdź, czy czujniki są dostępne."
        elif temp_out < 10:
            recommendation = "Wietrz krótko i intensywnie"
            reason = f"Na zewnątrz jest {temp_out:.1f}°C, a w domu {temp_in:.1f}°C. Otwórz szeroko okna na około 3–5 minut, a potem je zamknij, żeby nie wychłodzić pomieszczeń."
        elif temp_out < 18:
            recommendation = "Można krótko przewietrzyć"
            reason = f"Na zewnątrz jest {temp_out:.1f}°C, a w domu {temp_in:.1f}°C. Możesz krótko przewietrzyć dom, jeśli jakość powietrza i ryzyko pyłków są odpowiednie."
        elif temp_out < temp_in:
            recommendation = "Można chłodzić dom"
            reason = f"Na zewnątrz jest {temp_out:.1f}°C, a w domu {temp_in:.1f}°C — różnica wynosi {temp_in - temp_out:.1f}°C. Otwórz okna, jeśli chcesz obniżyć temperaturę."
        else:
            recommendation = "Ogranicz wietrzenie dla chłodzenia"
            reason = f"Na zewnątrz jest {temp_out:.1f}°C, a w domu {temp_in:.1f}°C. Ponieważ na zewnątrz nie jest chłodniej, ogranicz wietrzenie, jeśli nie musisz wymienić powietrza, by nie nagrzewać pomieszczeń."

        # Suppress routine ventilation while the heating circuit is active.
        # Humidity >= 60% remains an indoor-need override handled above.
        if boiler_raw.upper() == "HEATING" and (hum_in is None or hum_in < 60):
            recommendation = "Ogranicz wietrzenie — trwa ogrzewanie"
            if poor_air or pollen_high or pollen_present:
                reason = (
                    "Ogrzewanie pracuje, a powietrze na zewnątrz jest niekorzystne "
                    "z powodu zanieczyszczeń lub pyłków. Nie wietrz rutynowo. "
                    "Jeśli pojawi się pilna potrzeba wymiany powietrza, otwórz "
                    "okna szeroko tylko na kilka minut."
                )
            elif temp_in is not None and temp_out is not None and temp_out >= temp_in:
                reason = (
                    f"Ogrzewanie pracuje; w domu jest {temp_in:.1f}°C, "
                    f"na zewnątrz {temp_out:.1f}°C. Nie ma teraz powodu do "
                    "rutynowego wietrzenia — unikaj wychładzania lub dogrzewania "
                    "domu przez otwarte okna."
                )
            else:
                reason = (
                    "Ogrzewanie pracuje. Jeśli nie ma pilnej potrzeby wymiany "
                    "powietrza, pozostaw okna zamknięte. Gdy trzeba przewietrzyć, "
                    "wybierz krótkie, intensywne otwarcie zamiast uchylania okna."
                )

        # Add measured values only when the main explanation does not already
        # contain them. The same reason text is used by the card and notifications.
        if pollen_high or pollen_present:
            pollen_details = []
            if pollen_values[0] is not None:
                pollen_details.append(f"bieżące ryzyko: {pollen_values[0]}")
            if pollen_values[1] is not None:
                pollen_details.append(f"prognoza godzinowa: {pollen_values[1]}")
            if pollen_details:
                reason += " Dane pyłkowe — " + "; ".join(pollen_details) + "."
        if hum_in is not None and hum_in >= 60 and abs_humidity_in is not None and abs_humidity_out is not None:
            humidity_detail = (
                f"Wilgotność w domu: {hum_in:.0f}%; "
                if f"{hum_in:.0f}%" not in reason
                else ""
            )
            reason += (
                f" {humidity_detail}Wilgoć bezwzględna: dom "
                f"{abs_humidity_in:.1f} g/m³, zewnątrz {abs_humidity_out:.1f} g/m³."
            )
        if hum_in is not None and hum_in >= 60 and (poor_air or pollen_high or pollen_present):
            reason += " Jednocześnie trzeba uważać na zanieczyszczenia lub pyłki. Włącz wyciąg, ogranicz ich napływ i wietrz tylko krótko, gdy jest to potrzebne."
        if not pollution_known:
            reason += " Brakuje aktualnych danych o zanieczyszczeniach — zachowaj ostrożność."
        if not pollen_known:
            reason += " Brakuje aktualnych danych o pyłkach."
        if boiler_raw.upper() == "HEATING":
            reason += " Ogrzewanie pracuje — nie zostawiaj okien otwartych na długo."
        elif boiler_raw.upper() not in {"STANDBY", "IDLE", "OFF", "BRAK DANYCH", "UNKNOWN", "UNAVAILABLE", "OFFLINE"}:
            reason += " Sprawdź wskazanie obiegu grzewczego."
        if rain is not None and rain > 0:
            reason += f" W ostatniej godzinie odnotowano {rain:g} mm opadu — uważaj, żeby nie zalać pomieszczeń przez otwarte okna."
        reason += f" Uwzględniona pora roku: {season}; decyzja zależy przede wszystkim od pomiarów i potrzeby wymiany powietrza."

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
                "indoor_temperature_max": temp_in_max,
                "indoor_temperature_readings": valid_temperatures,
                "indoor_humidity": hum_in,
                "indoor_humidity_readings": valid_humidities,
                "indoor_room_readings": [
                    {
                        "name": room["name"],
                        "temperature": room["temperature"],
                        "humidity": room["humidity"],
                    }
                    for room in indoor_rooms
                    if room["temperature"] is not None or room["humidity"] is not None
                ],
                "outdoor_temperature": temp_out,
                "outdoor_humidity": hum_out,
                "indoor_absolute_humidity_g_m3": round(abs_humidity_in, 2) if abs_humidity_in is not None else None,
                "outdoor_absolute_humidity_g_m3": round(abs_humidity_out, 2) if abs_humidity_out is not None else None,
                "absolute_humidity_difference_g_m3": round(abs_humidity_in - abs_humidity_out, 2) if abs_humidity_in is not None and abs_humidity_out is not None else None,
                "pm2_5": pm25,
                "pm10": pm10,
                "air_quality_index": aqi,
                "air_quality_source": (
                    local_aqi_entity if local_aqi_used else options.get(CONF_AQI)
                ),
                "local_air_quality_index_raw": local_aqi_raw,
                "pollen_risk": pollen_values[0],
                "pollen_risk_hourly": pollen_values[1],
                "boiler_state": boiler,
                "rain_last_hour": rain,
                "pollution_data_available": pollution_known,
                "pollen_data_available": pollen_known,
                "pollution_threshold_pm2_5": pm25_limit,
                "pollution_threshold_pm10": pm10_limit,
                "poor_air_reasons": poor_air_reasons,
                "ventilation_flow_direction_available": False,
                "ventilation_flow_note": "Kierunek przepływu nie jest mierzony; zalecenie nie potwierdza, że kanał wyciąga powietrze.",
                "advice_is_medical": False,
            },
        }

    coordinator = DataUpdateCoordinator(
        hass,
        logger=logging.getLogger(__name__),
        config_entry=entry,
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
            CONF_INDOOR_TEMPERATURE_2,
            CONF_INDOOR_HUMIDITY_2,
            CONF_INDOOR_TEMPERATURE_3,
            CONF_INDOOR_HUMIDITY_3,
            CONF_OUTDOOR_TEMPERATURE,
            CONF_OUTDOOR_HUMIDITY,
            CONF_PM25,
            CONF_PM10,
            CONF_AQI,
            "sensor.ostrowiec_swietokrzyski_ul_polna_indeks_jakosci_powietrza",
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
        hass.async_create_task(coordinator.async_request_refresh())

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
