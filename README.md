# Klimat Domowy

Custom Home Assistant integration for indoor-air and ventilation guidance, with allergy-aware recommendations.

## Goals

- Configure source entities through the Home Assistant UI; no `configuration.yaml` edits.
- Publish one shared recommendation model for dashboard cards and automations.
- Handle unavailable or unknown source entities conservatively.
- Keep phone/device notification targets outside the integration so the engine remains independent of a particular phone.
- Extend later with ESPHome/ESP32 air-quality sensors.

## Current development status

Development version **0.1.0**. The first implementation provides a config flow, configurable source entities, configurable PM2.5/PM10 caution thresholds, and shared output sensors. It is an early development build and has not yet been tested in the user's live Home Assistant instance.

Expected entity IDs after setup:

- `sensor.klimat_domowy_zalecenie_wietrzenia` — the main recommendation.
- `sensor.klimat_domowy_ocena_powietrza_zewnetrznego` — outdoor pollution assessment.
- `sensor.klimat_domowy_ryzyko_alergiczne` — pollen-risk assessment.
- `sensor.klimat_domowy_temperatura_wewnetrzna`
- `sensor.klimat_domowy_wilgotnosc_wewnetrzna`
- `sensor.klimat_domowy_temperatura_zewnetrzna`
- `sensor.klimat_domowy_stan_obiegu_grzewczego`

The recommendation sensor exposes a `reason` attribute plus source readings and data-availability flags. Dashboard cards and automations should read these entities rather than reimplementing the decision logic.

Thresholds are caution thresholds, not guarantees of safety. The OpenWeatherMap air-pollution index is treated as its usual 1 (best) to 5 (worst) scale; the exact pollen entity state format must be checked against the installed integration before treating its risk classification as definitive.

## Installation (development)

Copy `custom_components/klimat_domowy` into `config/custom_components/klimat_domowy`, restart Home Assistant, then add **Klimat Domowy** under Settings → Devices & services → Add integration.

HACS metadata is present, but this repository is not yet a tested/released HACS version. Do not treat the current development build as production-ready until it has been validated in Home Assistant.

## Phone replacement and notifications

The integration itself does not send notifications and does not store phone IDs. Configure a Home Assistant automation to use the shared recommendation sensor and the notification service/group you maintain (currently `notify.cala_rodzina`). If that service is a manually configured group of mobile-app notify services, update its membership when phones are replaced.

## Safety notes

This integration provides guidance, not medical advice or a substitute for adequate ventilation. It does not replace certified carbon-monoxide or combustible-gas alarms. An outdoor-pollution warning should not be interpreted as a reason to tolerate dangerous indoor air; use appropriate ventilation/filtration and follow local health guidance.
