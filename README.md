# Klimat Domowy

Integracja Home Assistant zapewniająca zalecenia dotyczące wietrzenia i jakości powietrza z uwzględnieniem ryzyka alergicznego. Repozytorium jest przygotowane do instalacji jako własne repozytorium integracji w HACS; domyślne przypisania encji są przygotowane dla konkretnego domu.

## Goals

- Install with the household's preconfigured sensor mapping; source entities can be changed later in the Home Assistant UI. No `configuration.yaml` edits.
- Publish one shared recommendation model for dashboard cards and automations.
- Handle unavailable or unknown source entities conservatively.
- Send stable-recommendation notifications directly from the integration, with a configurable Home Assistant notify service.
- Extend later with ESPHome/ESP32 air-quality sensors.

## Current development status

Development version **0.2.15**. The implementation provides preconfigured source entities, editable options, up to three indoor temperature/humidity sensor pairs, configurable PM2.5/PM10 caution thresholds, absolute-humidity comparison, shared output sensors, a self-registering dashboard card, and built-in stable-recommendation notifications. It is a development build; automated checks run in GitHub Actions, but they do not replace a live test in the user's Home Assistant instance.

Expected entity IDs after setup:

- `sensor.klimat_domowy_zalecenie_wietrzenia` — the main recommendation.
- `sensor.klimat_domowy_ocena_powietrza_zewnetrznego` — outdoor pollution assessment.
- `sensor.klimat_domowy_ryzyko_alergiczne` — pollen-risk assessment.
- `sensor.klimat_domowy_temperatura_wewnetrzna`
- `sensor.klimat_domowy_wilgotnosc_wewnetrzna`
- `sensor.klimat_domowy_temperatura_zewnetrzna`
- `sensor.klimat_domowy_stan_obiegu_grzewczego`
- `button.klimat_domowy_test_powiadomienia` — immediate notification test.

The recommendation sensor exposes a `reason` attribute plus source readings, room-by-room readings, indoor/outdoor absolute humidity estimates, and data-availability flags. Indoor temperature is averaged across available configured sensors; the highest available indoor relative humidity is used for conservative moisture warnings. Absolute-humidity comparison uses only rooms with both temperature and humidity configured. The built-in dashboard card and notification system read the same coordinator output rather than reimplementing the decision logic. The `Test powiadomienia` button sends a message immediately without waiting for the normal notification delay; if it fails, the Home Assistant log records the configured target and exception. The card displays a concise explanation naming the decisive reading, pairs indoor and outdoor readings in two columns, and color-codes each metric by status; missing readings are grey. It includes PM2.5, PM10, AQI, pollen risk and hourly pollen forecast, heating-circuit state, and rainfall; unavailable readings are shown as missing rather than silently treated as zero.

Configure each temperature/humidity pair to refer to the same physical room. The first pair retains the existing default entity selections; the second and third pairs are optional and can be assigned to rooms such as the living room and bathroom. The current engine does not measure ventilation flow direction and cannot confirm that a vent is extracting air.

Thresholds are caution thresholds, not guarantees of safety. The OpenWeatherMap air-pollution index is treated as its usual 1 (best) to 5 (worst) scale; the pollen source uses the state `brak` to mean that no pollen was detected; this is displayed distinctly from unavailable or unknown source data.

## Instalacja przez HACS

1. Otwórz **HACS** i menu z trzema kropkami → **Repozytoria niestandardowe**.
2. Dodaj `https://github.com/MarLip1981/home-assistant-klimat-domowy` i wybierz kategorię **Integracja**.
3. Otwórz znalezione **Klimat Domowy** i wybierz **Pobierz**.
4. Uruchom ponownie Home Assistant.
5. Wejdź w **Ustawienia → Urządzenia i usługi → Dodaj integrację** i wybierz **Klimat Domowy**.

Nie trzeba kopiować plików ręcznie, edytować `configuration.yaml` ani wybierać kilkunastu encji podczas pierwszego uruchomienia. Integracja startuje z przygotowanymi domyślnymi przypisaniami czujników; można je później zmienić w opcjach integracji. Dodanie integracji w interfejsie Home Assistant jest jednorazowym krokiem wymaganym do utworzenia jej wpisu konfiguracyjnego.

Wersja rozwojowa 0.2.15 wymaga sprawdzenia działania w konkretnej instalacji Home Assistant. Testy CI nie zastępują testu powiadomień na skonfigurowanym telefonie.

## Dashboard card and notifications

The `Klimat Domowy` card is registered by the integration and should appear in the dashboard's Add card picker after the frontend loads the module. No separate Lovelace resource or manual card YAML is required. The card editor starts with the integration's output entities and allows mapping changes if entity IDs differ. Notifications are handled by the integration itself: the default target is `notify.cala_rodzina`, the default stability delay is 10 minutes, and both can be changed in the integration options. Notifications are sent only when a new recommendation remains unchanged for the configured delay; source attribute updates alone do not trigger another notification.

## Safety notes

This integration provides guidance, not medical advice or a substitute for adequate ventilation. It does not replace certified carbon-monoxide or combustible-gas alarms. An outdoor-pollution warning should not be interpreted as a reason to tolerate dangerous indoor air; use appropriate ventilation/filtration and follow local health guidance.
