# Klimat Domowy

Custom Home Assistant integration for indoor-air and ventilation guidance, with allergy-aware recommendations.

## Goals

- Configure entities through the Home Assistant UI; no `configuration.yaml` edits.
- Publish one shared recommendation model for dashboard cards and automations.
- Handle unavailable or unknown source entities conservatively.
- Keep notification destinations out of device-specific code so phones can be replaced independently.
- Extend later with ESPHome/ESP32 air-quality sensors.

## Initial development status

The first development release provides a config flow and sensors for a unified ventilation recommendation, indoor/outdoor conditions, air pollution and pollen risk. Thresholds are deliberately conservative and must be checked against the units and state values reported by the selected integrations.

## Installation (development)

Copy `custom_components/klimat_domowy` into `config/custom_components/klimat_domowy`, restart Home Assistant, then add **Klimat Domowy** under Settings → Devices & services → Add integration.

HACS distribution metadata and releases will be added after the first tested version.

## Safety notes

This integration provides guidance, not medical advice or a substitute for adequate ventilation. It does not replace certified carbon-monoxide or combustible-gas alarms. An air-pollution warning should not be interpreted as a reason to tolerate dangerous indoor air; use appropriate ventilation/filtration and follow local health guidance.
