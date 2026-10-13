/* Klimat Domowy — self-contained Lovelace card. */
const registerKlimatDomowyCard = () => {
  const DEFAULTS = {
    recommendation: "sensor.klimat_domowy_zalecenie_wietrzenia",
    airQuality: "sensor.klimat_domowy_ocena_powietrza_zewnetrznego",
    allergyRisk: "sensor.klimat_domowy_ryzyko_alergiczne",
    indoorTemperature: "sensor.klimat_domowy_temperatura_wewnetrzna",
    indoorHumidity: "sensor.klimat_domowy_wilgotnosc_wewnetrzna",
    outdoorTemperature: "sensor.klimat_domowy_temperatura_zewnetrzna",
  };

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

  class KlimatDomowyCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._config = { ...DEFAULTS };
      this._hass = undefined;
      this._lastMarkup = "";
    }

    setConfig(config) {
      this._config = { ...DEFAULTS, ...(config || {}) };
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      this._render();
    }

    get hass() {
      return this._hass;
    }

    getCardSize() {
      return 4;
    }

    static getConfigElement() {
      return document.createElement("klimat-domowy-card-editor");
    }

    static getStubConfig() {
      return { ...DEFAULTS };
    }

    _state(key) {
      return this._hass?.states?.[this._config[key]] || null;
    }

    _value(key, suffix = "") {
      const state = this._state(key);
      if (!state || ["unknown", "unavailable"].includes(state.state)) return "Brak danych";
      return `${state.state}${suffix}`;
    }

    _render() {
      if (!this.shadowRoot || !this._config) return;
      const recommendation = this._state("recommendation");
      const reason = recommendation?.attributes?.reason || "Brak dodatkowego wyjaśnienia.";
      const title = recommendation && !["unknown", "unavailable"].includes(recommendation.state)
        ? recommendation.state : "Oczekiwanie na dane";
      const air = this._value("airQuality");
      const allergy = this._value("allergyRisk");
      const indoorTemp = this._value("indoorTemperature", " °C");
      const indoorHumidity = this._value("indoorHumidity", "%");
      const outdoorTemp = this._value("outdoorTemperature", " °C");
      const attrs = recommendation?.attributes || {};
      const metric = (value, suffix = "") =>
        value === null || value === undefined || value === "" ? "Brak danych" : `${value}${suffix}`;
      const pm25 = metric(attrs.pm2_5, " µg/m³");
      const pm10 = metric(attrs.pm10, " µg/m³");
      const aqi = metric(attrs.air_quality_index);
      const outdoorHumidity = metric(attrs.outdoor_humidity, "%");
      const boiler = metric(attrs.boiler_state);
      const rain = metric(attrs.rain_last_hour, " mm");
      const indoorAbs = metric(attrs.indoor_absolute_humidity_g_m3, " g/m³");
      const outdoorAbs = metric(attrs.outdoor_absolute_humidity_g_m3, " g/m³");
      const pollen = metric(attrs.pollen_risk);
      const lowerTitle = title.toLowerCase();
      const warning = lowerTitle.includes("ogranicz")
        || lowerTitle.includes("pilnie")
        || lowerTitle.includes("wysokie ryzyko")
        || lowerTitle.includes("sprawdź czujniki")
        || lowerTitle.includes("pyłki wykryte")
        || lowerTitle.includes("obserwuj wilgotność");
      const pollenHourly = metric(attrs.pollen_risk_hourly);
      const pm25Limit = Number(attrs.pollution_threshold_pm2_5 ?? 15);
      const pm10Limit = Number(attrs.pollution_threshold_pm10 ?? 45);
      const numeric = (value) => {
        if (value === null || value === undefined || value === "") return null;
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
      };
      const tone = (value, good, elevated) => {
        const n = numeric(value);
        if (n === null) return "unknown";
        if (good(n)) return "good";
        if (elevated(n)) return "elevated";
        return "bad";
      };
      const tempInTone = tone(attrs.indoor_temperature, n => n >= 18 && n <= 26, n => n >= 16 && n <= 28);
      const tempOutTone = tone(attrs.outdoor_temperature, n => n >= 10 && n <= 25, n => n >= 5 && n <= 32);
      const humidityInTone = tone(attrs.indoor_humidity, n => n >= 40 && n <= 60, n => n >= 30 && n < 70);
      const humidityOutTone = tone(attrs.outdoor_humidity, n => n >= 30 && n <= 70, n => n >= 20 && n <= 85);
      const absDifference = numeric(attrs.absolute_humidity_difference_g_m3);
      const absInTone = absDifference === null ? "unknown" : absDifference >= 1 ? "good" : absDifference >= 0 ? "elevated" : "bad";
      const absOutTone = absDifference === null ? "unknown" : absDifference >= 1 ? "good" : absDifference >= 0 ? "elevated" : "bad";
      const pm25Tone = tone(attrs.pm2_5, n => n <= pm25Limit, n => n <= pm25Limit * 1.5);
      const pm10Tone = tone(attrs.pm10, n => n <= pm10Limit, n => n <= pm10Limit * 1.5);
      const aqiTone = tone(attrs.air_quality_index, n => n <= 2, n => n <= 3);
      const qualityText = String(air).toLowerCase();
      const airTone = air === "Brak danych" ? "unknown" : qualityText.includes("podwyższone") ? "bad" : "good";
      const pollenText = String(allergy).toLowerCase();
      const pollenTone = allergy === "Brak danych" || pollenText.includes("nieznany") ? "unknown"
        : pollenText.includes("wysokie") ? "bad"
        : pollenText.includes("wykryte") ? "elevated" : "good";
      const pollenHourlyText = String(pollenHourly).toLowerCase();
      const pollenHourlyTone = pollenHourly === "Brak danych" || pollenHourlyText.includes("nieznany") ? "unknown"
        : pollenHourlyText.includes("wysokie") ? "bad"
        : pollenHourlyText.includes("wykryte") ? "elevated" : "good";
      const boilerTone = boiler === "Brak danych" || boiler === "BRAK DANYCH" ? "unknown"
        : String(boiler).toUpperCase() === "HEATING" ? "elevated" : "good";
      const rainNumber = numeric(attrs.rain_last_hour);
      const rainTone = rainNumber === null ? "unknown" : rainNumber > 0 ? "elevated" : "good";
      const titleTone = warning ? "bad"
        : title.toLowerCase().includes("brak pełnych danych") ? "unknown"
        : "good";
      const tile = (label, value, toneName) =>
        `<div class="metric ${toneName}"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div></div>`;
      const markup = `
        <style>
          :host{display:block;color:var(--primary-text-color)}
          ha-card{overflow:hidden;border-radius:var(--ha-card-border-radius,12px)}
          .head{display:flex;align-items:center;gap:12px;padding:16px;color:var(--primary-text-color)}
          .head.good{background:color-mix(in srgb,var(--success-color,#2e7d32) 18%,var(--card-background-color))}
          .head.elevated{background:color-mix(in srgb,var(--warning-color,#edb62b) 25%,var(--card-background-color))}
          .head.bad{background:color-mix(in srgb,var(--error-color,#c62828) 24%,var(--card-background-color))}
          .head.unknown{background:var(--secondary-background-color)}
          .symbol{width:42px;height:42px;display:grid;place-items:center;border-radius:12px;
            background:rgba(127,127,127,.12);font-size:24px;flex-shrink:0}
          .eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.75}
          h2{font-size:19px;line-height:1.25;margin:3px 0 0;font-weight:600}
          .reason{padding:12px 16px 16px;line-height:1.45;color:var(--primary-text-color)}
          .status{margin:0 16px 12px;padding:7px 10px;border-radius:8px;font-size:12px;font-weight:700}
          .status.good{background:color-mix(in srgb,var(--success-color,#2e7d32) 18%,var(--card-background-color))}
          .status.elevated{background:color-mix(in srgb,var(--warning-color,#edb62b) 25%,var(--card-background-color))}
          .status.bad{background:color-mix(in srgb,var(--error-color,#c62828) 20%,var(--card-background-color))}
          .status.unknown{background:var(--secondary-background-color);color:var(--secondary-text-color)}
          .section{padding:0 16px 8px;font-size:12px;font-weight:700;letter-spacing:.04em;color:var(--secondary-text-color)}
          .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:0 16px 16px}
          .metric{padding:10px 12px;border-radius:10px;min-width:0;border:1px solid transparent}
          .metric.good{background:color-mix(in srgb,var(--success-color,#2e7d32) 14%,var(--card-background-color));border-color:color-mix(in srgb,var(--success-color,#2e7d32) 28%,transparent)}
          .metric.elevated{background:color-mix(in srgb,var(--warning-color,#edb62b) 20%,var(--card-background-color));border-color:color-mix(in srgb,var(--warning-color,#edb62b) 36%,transparent)}
          .metric.bad{background:color-mix(in srgb,var(--error-color,#c62828) 17%,var(--card-background-color));border-color:color-mix(in srgb,var(--error-color,#c62828) 32%,transparent)}
          .metric.unknown{background:var(--secondary-background-color);border-color:var(--divider-color,#777);border-style:dashed}
          .label{font-size:12px;color:var(--secondary-text-color);margin-bottom:5px}
          .value{font-size:15px;font-weight:600;overflow-wrap:anywhere}
          .foot{padding:0 16px 14px;font-size:11px;line-height:1.4;color:var(--secondary-text-color)}
          @media(max-width:360px){h2{font-size:17px}.grid{gap:6px;padding-left:10px;padding-right:10px}.metric{padding:9px}}
        </style>
        <ha-card>
          <div class="head ${titleTone}">
            <div class="symbol" aria-hidden="true">⌂</div>
            <div><div class="eyebrow">Klimat Domowy</div><h2>${esc(title)}</h2></div>
          </div>
          <div class="reason">${esc(reason)}</div>
          <div class="status ${titleTone}">${titleTone === "good" ? "WARUNKI SPRZYJAJĄ" : titleTone === "elevated" ? "ZACHOWAJ OSTROŻNOŚĆ" : titleTone === "bad" ? "WYMAGA UWAGI" : "BRAK PEŁNYCH DANYCH"}</div>
          <div class="section">DOM I ZEWNĄTRZ</div>
          <div class="grid">
            ${tile("Temperatura w domu", indoorTemp, tempInTone)}
            ${tile("Temperatura na zewnątrz", outdoorTemp, tempOutTone)}
            ${tile("Wilgotność w domu", indoorHumidity, humidityInTone)}
            ${tile("Wilgotność na zewnątrz", outdoorHumidity, humidityOutTone)}
            ${tile("Wilgoć bezwzględna — dom", indoorAbs, absInTone)}
            ${tile("Wilgoć bezwzględna — zewnątrz", outdoorAbs, absOutTone)}
          </div>
          <div class="section">POZOSTAŁE ODCZYTY</div>
          <div class="grid">
            ${tile("Jakość powietrza", air, airTone)}
            ${tile("Ryzyko pyłkowe", allergy, pollenTone)}
            ${tile("PM2.5", pm25, pm25Tone)}
            ${tile("PM10", pm10, pm10Tone)}
            ${tile("Indeks jakości powietrza", aqi, aqiTone)}
            ${tile("Pyłki — prognoza godzinowa", pollenHourly, pollenHourlyTone)}
            ${tile("Obieg grzewczy", boiler, boilerTone)}
            ${tile("Opady w ostatniej godzinie", rain, rainTone)}
          </div>
          <div class="foot">Zielony — dobrze · żółty — podwyższony poziom · czerwony — źle · szary — brak odczytu. Brak danych nie oznacza czystego powietrza.</div>
        </ha-card>`;

      if (markup !== this._lastMarkup) {
        this.shadowRoot.innerHTML = markup;
        this._lastMarkup = markup;
      }
    }
  }

  class KlimatDomowyCardEditor extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._config = { ...DEFAULTS };
      this._hass = undefined;
    }

    setConfig(config) {
      this._config = { ...DEFAULTS, ...(config || {}) };
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      this.shadowRoot?.querySelectorAll("ha-entity-picker").forEach((picker) => {
        picker.hass = hass;
      });
    }

    _render() {
      if (!this.shadowRoot) return;
      const fields = [
        ["recommendation", "Główne zalecenie"],
        ["airQuality", "Ocena powietrza zewnętrznego"],
        ["allergyRisk", "Ryzyko pyłkowe"],
        ["indoorTemperature", "Temperatura wewnętrzna"],
        ["indoorHumidity", "Wilgotność wewnętrzna"],
        ["outdoorTemperature", "Temperatura zewnętrzna"],
      ];
      this.shadowRoot.innerHTML = `
        <style>
          :host{display:block}.field{display:block;margin:12px 0}
          .label{display:block;margin-bottom:6px;font-weight:500}
          ha-entity-picker{display:block;width:100%}
          p{color:var(--secondary-text-color);line-height:1.45}
        </style>
        <p>Domyślne encje są już przypisane. Zmieniaj je tylko wtedy, gdy zmienisz czujniki lub identyfikatory encji.</p>
        ${fields.map(([key,label]) => `<label class="field"><span class="label">${label}</span><ha-entity-picker data-key="${key}" label="${label}"></ha-entity-picker></label>`).join("")}`;
      this.shadowRoot.querySelectorAll("ha-entity-picker").forEach((picker) => {
        const key = picker.dataset.key;
        picker.hass = this._hass;
        picker.value = this._config[key] || "";
        picker.addEventListener("value-changed", (event) => {
          const value = event.detail?.value || "";
          this._config = { ...this._config, [key]: value };
          this.dispatchEvent(new CustomEvent("config-changed", {
            bubbles: true, composed: true, detail: { config: { ...this._config } },
          }));
        });
      });
    }
  }

  if (!customElements.get("klimat-domowy-card")) {
    customElements.define("klimat-domowy-card", KlimatDomowyCard);
  }
  if (!customElements.get("klimat-domowy-card-editor")) {
    customElements.define("klimat-domowy-card-editor", KlimatDomowyCardEditor);
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === "klimat-domowy-card")) {
    window.customCards.push({
      type: "klimat-domowy-card",
      name: "Klimat Domowy",
      description: "Zalecenia wietrzenia, wilgotność, jakość powietrza i pyłki.",
      preview: true,
      documentationURL: "https://github.com/MarLip1981/home-assistant-klimat-domowy",
    });
  }
};

// Register immediately for dashboards that are already being built, then retry
// after Home Assistant's startup/polyfill phase. On affected frontend versions,
// the first definition can be lost when the scoped registry replaces the native one.
registerKlimatDomowyCard();
if (document.readyState === "complete") {
  window.setTimeout(registerKlimatDomowyCard, 0);
} else {
  window.addEventListener("load", registerKlimatDomowyCard, { once: true });
}
