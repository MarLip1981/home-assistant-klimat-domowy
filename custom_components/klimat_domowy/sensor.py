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
                "name": "główny czujnik",
                "temperature": _number(state_for(CONF_INDOOR_TEMPERATURE)),
                "humidity": _number(state_for(CONF_INDOOR_HUMIDITY)),
            },
            {
                "name": "drugi czujnik",
                "temperature": _number(state_for(CONF_INDOOR_TEMPERATURE_2)),
                "humidity": _number(state_for(CONF_INDOOR_HUMIDITY_2)),
            },
            {
                "name": "trzeci czujnik",
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

        pollen_known = any(_pollen_is_known(value) for value in pollen_values)
        pollen_none_detected = any(_pollen_is_none_detected(value) for value in pollen_values)
        pollen_high = any(_pollen_is_high(value) for value in pollen_values)
        pollen_low = any(_pollen_is_low(value) for value in pollen_values)
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
        elif pollen_none_detected:
            allergy_risk = "Brak wykrytych pyłków"
        elif pollen_low:
            allergy_risk = "Niskie"
        else:
            allergy_risk = "Poziom ryzyka nieznany"

        data_incomplete = not valid_temperatures or not valid_humidities or temp_out is None
        if hum_in is not None and hum_in >= 70:
            recommendation = "Pilnie ogranicz wilgoć"
            if abs_humidity_in is not None and abs_humidity_out is not None and abs_humidity_out <= abs_humidity_in - 1.0:
                reason = (
                    "Wilgotność wewnętrzna jest bardzo wysoka, a powietrze zewnętrzne ma "
                    "wyraźnie mniej wilgoci bezwzględnej. Jeśli jakość powietrza i pyłki "
                    "na to pozwalają, krótko przewietrz; użyj też wyciągu i sprawdź źródła wilgoci."
                )
            else:
                reason = (
                    "Wilgotność wewnętrzna jest bardzo wysoka. Sprawdź skuteczność i kierunek przepływu wyciągu "
                    "i sprawdź źródła wilgoci. Nie zakładaj, że samo otwarcie okna osuszy "
                    "dom — wilgotność bezwzględna na zewnątrz nie jest wyraźnie niższa "
                    "albo brakuje danych do porównania."
                )
        elif hum_in is not None and hum_in >= 60:
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
        elif poor_air:
            recommendation = "Ogranicz wietrzenie — zanieczyszczenia"
            reason = "Podwyższone wskazania: " + ", ".join(poor_air_reasons) + ". Wietrz niezbędnie i krótko; rozważ filtrację."
            if pollen_high:
                reason += " Dodatkowo źródło pyłkowe wskazuje wysokie ryzyko alergiczne."
            elif pollen_present:
                reason += " Dodatkowo wykryto pyłki; poziom ryzyka wymaga weryfikacji."
        elif pollen_high:
            recommendation = "Wietrz krótko — wysokie ryzyko pyłków"
            reason = "Dane o pyłkach wskazują wysokie ryzyko alergiczne."
        elif pollen_present:
            recommendation = "Wietrz krótko — pyłki wykryte"
            reason = "Źródło wskazuje obecność pyłków, ale poziom ryzyka nie jest jednoznaczny. Wietrz krótko i obserwuj własną reakcję."
        elif data_incomplete:
            recommendation = "Sprawdź czujniki — brak pełnych danych"
            reason = "Brakuje temperatury wewnętrznej/zewnętrznej lub wilgotności wewnętrznej."
        elif temp_out < 10:
            recommendation = "Wietrz krótko i intensywnie"
            reason = "Na zewnątrz jest chłodno. Otwórz okna szeroko na około 3–5 minut, najlepiej po przeciwnych stronach mieszkania, jeśli to możliwe, aby uzyskać szybki przepływ powietrza. Nie uchylaj ich na długo i nie machaj nimi — chodzi o krótką, mocną wymianę powietrza. Jeśli jakość powietrza lub ryzyko pyłków są podwyższone, ogranicz wietrzenie i kieruj się tym ostrzeżeniem."
        elif temp_out < 18:
            recommendation = "Można krótko przewietrzyć"
            reason = "Umiarkowana temperatura zewnętrzna sprzyja krótkiej wymianie powietrza, jeśli nie ma innych przeciwwskazań."
        elif temp_out < temp_in:
            recommendation = "Można chłodzić dom"
            reason = "Na zewnątrz jest chłodniej niż wewnątrz; korzystaj z tego, jeśli potrzebujesz obniżyć temperaturę."
        else:
            recommendation = "Ogranicz wietrzenie dla chłodzenia"
            reason = "Na zewnątrz nie jest chłodniej niż w domu. Wietrz nadal, gdy wymaga tego jakość powietrza wewnętrznego."

        if hum_in is not None and hum_in >= 60 and (poor_air or pollen_high or pollen_present):
            conflicts = []
            if poor_air:
                conflicts.append("podwyższone zanieczyszczenia: " + ", ".join(poor_air_reasons))
            if pollen_high:
                conflicts.append("wysokie ryzyko pyłków")
            elif pollen_present:
                conflicts.append("wykryte pyłki o niejednoznacznym poziomie ryzyka")
            reason += (
                " Jednocześnie występuje " + " oraz ".join(conflicts) + ". "
                "Nie ignoruj problemu wilgoci, ale nie zakładaj też, że otwarcie okna jest "
                "najlepszym rozwiązaniem. Sprawdź skuteczność i kierunek przepływu wentylacji; "
                "ogranicz napływ zanieczyszczeń i rozważ filtrację."
            )
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

        # Every recommendation should explain itself using the actual readings,
        # not only a generic sentence. Keep raw values and configured thresholds
        # visible so the user can judge why the advice was produced.
        def reading(value: float | None, unit: str = "") -> str:
            return "brak danych" if value is None else f"{value:.1f}{unit}"

        context = [
            f"temperatura w domu {reading(temp_in, ' °C')}",
            f"maksymalna z dostępnych temperatur pokojowych {reading(temp_in_max, ' °C')}",
            f"wilgotność wewnętrzna {reading(hum_in, '%')}",
            f"temperatura zewnętrzna {reading(temp_out, ' °C')}",
            f"wilgotność zewnętrzna {reading(hum_out, '%')}",
            (
                "różnica wilgoci bezwzględnej (dom minus zewnątrz) "
                f"{reading(abs_humidity_in - abs_humidity_out, ' g/m³')}"
                if abs_humidity_in is not None and abs_humidity_out is not None
                else "różnica wilgoci bezwzględnej: brak danych do porównania"
            ),
            f"PM2.5 {reading(pm25, ' µg/m³')} (próg {pm25_limit:g} µg/m³)",
            f"PM10 {reading(pm10, ' µg/m³')} (próg {pm10_limit:g} µg/m³)",
            f"indeks jakości powietrza {reading(aqi)} (wartości 3–5 traktowane jako podwyższone)",
            f"ryzyko pyłkowe: {pollen_values[0] or 'brak danych'}",
            f"prognoza godzinowa pyłków: {pollen_values[1] or 'brak danych'}",
        ]
        reason += "\n\nOdczyty, na których oparto zalecenie: " + "; ".join(context) + "."
        if poor_air:
            reason += (
                " Ponieważ co najmniej jeden wskaźnik przekracza przyjęty próg, "
                "nie wietrz długo ani przy uchylonym oknie; jeśli trzeba wymienić powietrze, "
                "zrób to krótko i intensywnie, a przy objawach lub bardzo złym powietrzu "
                "rozważ filtrację i ponowną ocenę odczytów."
            )
        elif pollen_high or pollen_present:
            reason += (
                " Ze względu na sygnał pyłkowy wybierz moment o niższym ryzyku, jeśli źródło "
                "pokazuje taką zmianę. Sam odczyt pyłków nie określa indywidualnej reakcji alergicznej."
            )
        if hum_in is not None and hum_in >= 60:
            reason += (
                " Wilgotność względna powyżej 60% uzasadnia sprawdzenie źródeł wilgoci "
                "i działania wyciągu; przy porównaniu osuszania ważniejsza jest wilgoć bezwzględna "
                "niż sama wilgotność względna."
            )

        # Build a useful explanation: explain the decision, quote the readings
        # that matter, and mention important competing factors without dumping
        # every available sensor into one long paragraph.
        if hum_in is not None and hum_in >= 70:
            reason = (
                f"W domu wilgotność wynosi {hum_in:.0f}%, czyli jest bardzo wysoka "
                "(warto dążyć do około 40–60%). Włącz wyciąg i sprawdź źródło wilgoci, "
                "np. gotowanie, suszenie prania lub słabą wentylację."
            )
            if abs_humidity_in is not None and abs_humidity_out is not None:
                difference = abs_humidity_in - abs_humidity_out
                if difference >= 1.0:
                    reason += (
                        f" Powietrze w domu zawiera {abs_humidity_in:.1f} g/m³ wody, "
                        f"a na zewnątrz {abs_humidity_out:.1f} g/m³ — na zewnątrz jest "
                        f"o {difference:.1f} g/m³ mniej wilgoci, więc krótkie, intensywne "
                        "wietrzenie może pomóc, o ile powietrze zewnętrzne jest odpowiednie."
                    )
                else:
                    reason += (
                        f" Wilgoć bezwzględna wynosi {abs_humidity_in:.1f} g/m³ w domu "
                        f"i {abs_humidity_out:.1f} g/m³ na zewnątrz, więc samo otwarcie "
                        "okna nie daje wyraźnej przewagi w osuszaniu."
                    )
        elif hum_in is not None and hum_in >= 60:
            reason = (
                f"W domu wilgotność wynosi {hum_in:.0f}%, czyli przekracza zalecany "
                "przedział 40–60%. Warto ograniczyć źródła wilgoci i korzystać z wyciągu."
            )
            if abs_humidity_in is not None and abs_humidity_out is not None:
                difference = abs_humidity_in - abs_humidity_out
                if difference >= 1.0:
                    reason += (
                        f" W domu jest {abs_humidity_in:.1f} g/m³ wilgoci, a na zewnątrz "
                        f"{abs_humidity_out:.1f} g/m³; różnica {difference:.1f} g/m³ "
                        "przemawia za krótkim wietrzeniem, jeśli zanieczyszczenia i pyłki są niskie."
                    )
                else:
                    reason += (
                        f" Wilgoć bezwzględna: {abs_humidity_in:.1f} g/m³ w domu i "
                        f"{abs_humidity_out:.1f} g/m³ na zewnątrz. Powietrze zewnętrzne "
                        "nie jest wyraźnie suchsze, więc wyciąg może być lepszym wyborem."
                    )
            else:
                reason += " Brakuje danych o wilgoci bezwzględnej, więc nie da się ocenić, czy wietrzenie osuszy dom."
        elif poor_air:
            decisive = []
            if pm25 is not None:
                decisive.append(f"PM2.5 {pm25:.1f} µg/m³ (próg {pm25_limit:g})")
            if pm10 is not None:
                decisive.append(f"PM10 {pm10:.1f} µg/m³ (próg {pm10_limit:g})")
            if aqi is not None:
                decisive.append(f"indeks jakości powietrza {aqi:.0f}/5")
            reason = (
                "Ogranicz długie wietrzenie, ponieważ "
                + ", ".join(decisive)
                + " wskazuje na podwyższone zanieczyszczenie. Jeśli trzeba wymienić powietrze, "
                "zrób to krótko; przy dostępnej filtracji rozważ jej użycie."
            )
        elif pollen_high:
            reason = (
                f"Źródło pyłkowe wskazuje wysokie ryzyko ({pollen_values[0]}). "
                "Ogranicz długie wietrzenie i, jeśli prognoza godzinowa pokazuje niższe ryzyko, "
                "wybierz spokojniejszą porę."
            )
        elif pollen_present:
            reason = (
                f"Źródło wykrywa pyłki ({pollen_values[0]}), ale sam ten odczyt nie określa "
                "dokładnie siły ryzyka. Wietrz krótko i zwróć uwagę na objawy alergii."
            )
        elif data_incomplete:
            missing = []
            if not valid_temperatures:
                missing.append("temperatury w domu")
            if not valid_humidities:
                missing.append("wilgotności w domu")
            if temp_out is None:
                missing.append("temperatury na zewnątrz")
            reason = (
                "Nie mogę rzetelnie dobrać wietrzenia, bo brakuje odczytu: "
                + ", ".join(missing)
                + ". Sprawdź te czujniki; brak danych nie oznacza prawidłowych warunków."
            )
        elif temp_out < 10:
            reason = (
                f"Na zewnątrz jest {temp_out:.1f}°C. Jeśli potrzebujesz wymienić powietrze, "
                "otwórz okna szeroko na około 3–5 minut zamiast długo ich uchylać — "
                "to ogranicza wychładzanie ścian i mebli."
            )
        elif temp_out < 18:
            reason = (
                f"Na zewnątrz jest {temp_out:.1f}°C. Krótkie wietrzenie może odświeżyć dom "
                "bez tak dużych strat ciepła jak długie uchylanie okna."
            )
        elif temp_out < temp_in:
            reason = (
                f"W domu jest średnio {temp_in:.1f}°C, a na zewnątrz {temp_out:.1f}°C. "
                "Chłodniejsze powietrze może obniżyć temperaturę w domu; wietrz wtedy, "
                "gdy chcesz go schłodzić lub wymienić zużyte powietrze."
            )
        else:
            reason = (
                f"W domu jest średnio {temp_in:.1f}°C, a na zewnątrz {temp_out:.1f}°C, "
                "więc wietrzenie nie schłodzi teraz skutecznie pomieszczeń. Nadal wymieniaj "
                "powietrze, gdy jest taka potrzeba, ale unikaj długiego uchylania okien."
            )

        # Add only relevant context, so the explanation remains readable.
        if hum_in is not None and hum_in < 60:
            reason += f" Wilgotność w domu wynosi {hum_in:.0f}% — mieści się poniżej progu podwyższonej wilgotności."
        if poor_air and hum_in is not None and hum_in >= 60:
            reason += " Ponieważ powietrze zewnętrzne jest zanieczyszczone, przy wilgoci w domu najpierw użyj wyciągu i ogranicz napływ zanieczyszczeń."
        elif (pollen_high or pollen_present) and hum_in is not None and hum_in >= 60:
            reason += " Przy podwyższonej wilgotności użyj wyciągu; z wietrzeniem zachowaj ostrożność ze względu na pyłki."
        if not pollution_known:
            reason += " Nie ma odczytu zanieczyszczeń, więc nie można potwierdzić, że powietrze na zewnątrz jest czyste."
        if not pollen_known:
            reason += " Brakuje danych o pyłkach; nie należy tego traktować jako potwierdzenia braku alergenów."

        # When outdoor conditions are not flagged as poor, show the values
        # behind that assessment too, so "no warning" is not an unexplained verdict.
        if pollution_known and not poor_air:
            normal_air_readings = []
            if pm25 is not None:
                normal_air_readings.append(f"PM2.5 {pm25:.1f} µg/m³ przy progu {pm25_limit:g}")
            if pm10 is not None:
                normal_air_readings.append(f"PM10 {pm10:.1f} µg/m³ przy progu {pm10_limit:g}")
            if aqi is not None:
                normal_air_readings.append(f"indeks jakości {aqi:.0f}/5")
            reason += (
                " Odczyty zanieczyszczeń: " + ", ".join(normal_air_readings)
                + "; żaden z dostępnych wskaźników nie przekracza ustawionych progów."
            )
        if pollen_known and not (pollen_high or pollen_present):
            pollen_description = pollen_values[0] or pollen_values[1] or "brak szczegółowego opisu"
            forecast_description = (
                f"; prognoza godzinowa: {pollen_values[1]}"
                if pollen_values[1] else ""
            )
            reason += (
                f" Pyłki: bieżące źródło podaje „{pollen_description}”"
                f"{forecast_description}. To opis źródła, nie gwarancja braku objawów."
            )

        if len(valid_temperatures) > 1 and max(valid_temperatures) - min(valid_temperatures) >= 2.0:
            reason += (
                f" Czujniki pokazują różnicę temperatur w domu "
                f"{max(valid_temperatures) - min(valid_temperatures):.1f}°C; "
                "sprawdź, czy pomieszczenia nie nagrzewają się lub nie wychładzają nierówno."
            )
        if boiler.upper() == "HEATING":
            reason += " Obieg grzewczy aktualnie grzeje — unikaj długiego wietrzenia, by nie wychładzać domu."
        if rain is not None and rain > 0:
            reason += " W ostatniej godzinie odnotowano opad; pamiętaj, by deszcz nie dostał się przez otwarte okna."

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
