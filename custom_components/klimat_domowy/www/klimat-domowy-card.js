/* Klimat Domowy — self-contained Lovelace card. */
(() => {
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
      const lowerTitle = title.toLowerCase();
      const warning = lowerTitle.includes("ogranicz")
        || lowerTitle.includes("pilnie")
        || lowerTitle.includes("wysokie ryzyko")
        || lowerTitle.includes("sprawdź czujniki");
      this.shadowRoot.innerHTML = `
        <style>
          :host{display:block;color:var(--primary-text-color)}
          ha-card{overflow:hidden;border-radius:var(--ha-card-border-radius,12px)}
          .head{display:flex;align-items:center;gap:12px;padding:16px 16px 8px}
          .symbol{width:42px;height:42px;display:grid;place-items:center;border-radius:12px;
            background:var(--secondary-background-color);font-size:24px;flex-shrink:0}
          .eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--secondary-text-color)}
          h2{font-size:19px;line-height:1.25;margin:3px 0 0;font-weight:600}
          .reason{padding:12px 16px 16px;line-height:1.5;color:var(--primary-text-color)}
          .status{margin:8px 16px 0;padding:8px 10px;border-radius:8px;
            background:${warning ? "var(--warning-color, #b87516)" : "var(--secondary-background-color)"};
            color:${warning ? "white" : "var(--secondary-text-color)"};font-size:12px;font-weight:600}
          .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:0 16px 16px}
          .metric{padding:10px 12px;background:var(--secondary-background-color);border-radius:10px;min-width:0}
          .label{font-size:12px;color:var(--secondary-text-color);margin-bottom:5px}
          .value{font-size:15px;font-weight:600;overflow-wrap:anywhere}
          .foot{padding:0 16px 14px;font-size:11px;line-height:1.4;color:var(--secondary-text-color)}
          @media(max-width:360px){h2{font-size:17px}.grid{grid-template-columns:1fr}}
        </style>
        <ha-card>
          <div class="head">
            <div class="symbol" aria-hidden="true">⌂</div>
            <div><div class="eyebrow">Klimat Domowy</div><h2>${esc(title)}</h2></div>
          </div>
          <div class="status">${warning ? "WYMAGA UWAGI" : "AKTUALNE ZALECENIE"}</div>
          <div class="reason">${esc(reason)}</div>
          <div class="grid">
            <div class="metric"><div class="label">Temperatura w domu</div><div class="value">${esc(indoorTemp)}</div></div>
            <div class="metric"><div class="label">Wilgotność w domu</div><div class="value">${esc(indoorHumidity)}</div></div>
            <div class="metric"><div class="label">Temperatura na zewnątrz</div><div class="value">${esc(outdoorTemp)}</div></div>
            <div class="metric"><div class="label">Jakość powietrza</div><div class="value">${esc(air)}</div></div>
            <div class="metric"><div class="label">Ryzyko pyłkowe</div><div class="value">${esc(allergy)}</div></div>
          </div>
          <div class="foot">Zalecenia pomocnicze, nie medyczne. Kierunek przepływu wentylacji nie jest mierzony.</div>
        </ha-card>`;
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
})();
