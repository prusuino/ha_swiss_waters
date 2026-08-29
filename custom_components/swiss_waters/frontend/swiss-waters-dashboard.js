/* =====================================================================
 * Swiss Waters (BAFU) — dashboard strategy
 * =====================================================================
 * This file registers a Lovelace dashboard strategy only; the integration
 * has no custom card. Register it once as a Lovelace resource (see the
 * README) and Home Assistant offers "Swiss Waters" under "Add dashboard".
 *
 * The shared core and the strategy sit inside one IIFE so their names never
 * collide with another integration shipping the same core in the global
 * scope.
 * ===================================================================== */
(() => {
/* =====================================================================
 * Dashboard strategy core — shared building blocks
 * =====================================================================
 * A Lovelace dashboard strategy generates a dashboard in the browser at
 * render time. Nothing is written to .storage: the dashboard belongs to
 * the user, the integration only supplies the recipe.
 *
 * ⚠️ This block is duplicated into every integration that ships a
 * strategy. Each integration is its own HACS repository and must not
 * depend on another one being installed, so a shared file is not an
 * option. Keep the copies in sync and bump CORE_VERSION when the shared
 * part changes — it identifies which revision a copy was taken from.
 * ===================================================================== */

const CORE_VERSION = "1.1.1";

/* 1.1.1 - review follow-ups on the `strategy:` options
 *   (a) `map: false` only dropped the view with path "map". Where the map is
 *       a section inside another view (or a card in a panel view) it stayed
 *       visible. The option now also strips map cards out of every view: a
 *       section left with nothing but headings is dropped, and a view that
 *       ends up without any sections or cards is dropped as well.
 *   (b) The view flavour hardcoded max_columns: 2 and discarded the user's
 *       `max_columns`. It now uses the option when valid, else the value of
 *       the first sections view, else 2.
 *   (c) The view flavour copied only sections and cards, losing a view's
 *       `header` and `badges`. Both are carried over from the first view
 *       that has them. */

/* --- Registry access -------------------------------------------------
 * The registries are the only reliable way to find an integration's
 * entities: entity_id patterns are user-editable, unique_id is not.
 * Both calls are cheap and cached by the frontend for the render pass.
 */
async function loadRegistry(hass) {
  const [entities, devices] = await Promise.all([
    hass.callWS({ type: "config/entity_registry/list" }),
    hass.callWS({ type: "config/device_registry/list" }),
  ]);
  return { entities, devices };
}

/** All registry entries belonging to one integration (platform == domain). */
function entriesOfDomain(entities, domain) {
  return entities.filter((e) => e.platform === domain && !e.disabled_by);
}

/** Registry entries of one config entry, keyed by unique_id suffix.
 *  Mirrors the `f"{entry_id}_{suffix}"` convention the integrations use. */
function bySuffix(entities, configEntryId) {
  const out = {};
  const prefix = `${configEntryId}_`;
  for (const e of entities) {
    if (e.config_entry_id !== configEntryId) continue;
    if (typeof e.unique_id === "string" && e.unique_id.startsWith(prefix)) {
      out[e.unique_id.slice(prefix.length)] = e.entity_id;
    }
  }
  return out;
}

/** Group an integration's entities by the device they belong to.
 *  Returns [{device, entities:[registryEntry,...]}] sorted by device name. */
function groupByDevice(domainEntries, devices) {
  const byId = new Map(devices.map((d) => [d.id, d]));
  const groups = new Map();
  for (const e of domainEntries) {
    if (!e.device_id) continue;
    if (!groups.has(e.device_id)) groups.set(e.device_id, []);
    groups.get(e.device_id).push(e);
  }
  return [...groups.entries()]
    .map(([id, list]) => ({ device: byId.get(id), entities: list }))
    .filter((g) => g.device)
    .sort((a, b) => deviceName(a.device).localeCompare(deviceName(b.device)));
}

function deviceName(device) {
  return device.name_by_user || device.name || "";
}

/* --- Card helpers ---------------------------------------------------- */

const heading = (text, icon, badges) => {
  const card = { type: "heading", heading: text };
  if (icon) card.icon = icon;
  if (badges && badges.length) card.badges = badges;
  return card;
};

const grid = (cards, columnSpan) => {
  const section = { type: "grid", cards: cards.filter(Boolean) };
  if (columnSpan) section.column_span = columnSpan;
  return section;
};

const tile = (entity, extra = {}) => ({ type: "tile", entity, ...extra });

/** Map card fed from the integration's geo_location source.
 *  Deliberately uses geo_location_sources instead of an entity list: the
 *  markers are hidden entities, and the source keeps working when the
 *  set of markers changes between renders.
 *  labelAttribute writes the marker label into the source object, which is
 *  where the map card reads a geo-location source's label config from — the
 *  card-level label_mode only applies to `entities`. */
const mapCard = (domain, opts = {}) => ({
  type: "map",
  geo_location_sources: [
    opts.labelAttribute
      ? { source: domain, label_mode: "attribute", attribute: opts.labelAttribute }
      : domain,
  ],
  entities: opts.entities || ["zone.home"],
  default_zoom: opts.zoom ?? 8,
  theme_mode: "auto",
  grid_options: { columns: 12, rows: opts.rows ?? 6 },
});

/** Shown instead of an empty dashboard — an empty dashboard looks broken
 *  and gives the user nothing to act on. */
const emptyNotice = (text) => ({
  type: "markdown",
  content: text,
});

/* --- Localisation ----------------------------------------------------
 * Strategies run in the frontend, so hass.language is authoritative.
 * Falls back to English for any language the integration does not ship.
 */
function translator(strings, hass) {
  const lang = (hass.language || "en").split("-")[0];
  const table = strings[lang] || strings.en;
  return (key) => (table && table[key]) || (strings.en && strings.en[key]) || key;
}

/* --- Strategy base ---------------------------------------------------
 * Wraps the parts every strategy repeats: load registries, bail out
 * gracefully when the integration is not set up, and hand the concrete
 * strategy a prepared context.
 */

/* Options a user may put under `strategy:` in the raw configuration editor.
 * They are handled here in the core, so every integration supports the same
 * set without shipping its own option code:
 *
 *   map: false        drop the map: the full-screen map view as well as the
 *                     map cards inside section and panel views
 *   title: "..."      override the title
 *   max_columns: 3    column count of the generated section views (the view
 *                     flavour honours it too)
 *
 * Unknown keys are ignored on purpose - a strategy config is free-form, and a
 * typo should not take the dashboard down. */
const validColumns = (value) => {
  const cols = Number(value);
  return Number.isFinite(cols) && cols > 0 ? cols : undefined;
};

const isMapCard = (card) => Boolean(card) && card.type === "map";
const isHeadingCard = (card) => Boolean(card) && card.type === "heading";

/* Remove the map cards of one view. A section is dropped once only headings
 * remain - a heading merely labels the map that was just removed. Returns
 * null when nothing is left to show; views without a map card come back
 * untouched. */
const withoutMapCards = (view) => {
  let touched = false;
  const out = { ...view };
  if (Array.isArray(view.sections)) {
    out.sections = [];
    for (const section of view.sections) {
      const cards = Array.isArray(section.cards) ? section.cards : [];
      if (!cards.some(isMapCard)) {
        out.sections.push(section);
        continue;
      }
      touched = true;
      const rest = cards.filter((c) => !isMapCard(c));
      if (rest.some((c) => !isHeadingCard(c))) out.sections.push({ ...section, cards: rest });
    }
  }
  if (Array.isArray(view.cards) && view.cards.some(isMapCard)) {
    touched = true;
    out.cards = view.cards.filter((c) => !isMapCard(c));
  }
  if (!touched) return view;
  const empty = !(out.sections && out.sections.length) && !(out.cards && out.cards.length);
  return empty ? null : out;
};

const applyViewOptions = (views, config) => {
  const cfg = config || {};
  let out = views;
  if (cfg.map === false) {
    out = out
      .filter((v) => v.path !== "map")
      .map(withoutMapCards)
      .filter(Boolean);
  }
  const cols = validColumns(cfg.max_columns);
  if (cols) {
    out = out.map((v) => (v.type === "sections" ? { ...v, max_columns: cols } : v));
  }
  return out;
};

/* A view strategy must return exactly ONE view, while build() yields a list.
 * Section views are merged by concatenating their sections. A panel view (the
 * map) has no sections, so its cards become one full-width section instead -
 * that keeps the map visible rather than silently dropping it. */
const flattenToView = (views, title, icon, config) => {
  const sections = [];
  for (const v of views) {
    if (Array.isArray(v.sections) && v.sections.length) {
      sections.push(...v.sections);
    } else if (Array.isArray(v.cards) && v.cards.length) {
      sections.push(
        grid(
          v.cards.map((c) => ({
            ...c,
            grid_options: { columns: "full", rows: (c.grid_options || {}).rows ?? 8 },
          }))
        )
      );
    }
  }
  const sized = views.find((v) => v.type === "sections" && validColumns(v.max_columns));
  const view = {
    title,
    icon,
    type: "sections",
    max_columns: validColumns((config || {}).max_columns) ?? (sized ? validColumns(sized.max_columns) : 2),
    sections,
  };
  // header and badges live outside the sections and would be lost by the
  // merge above - keep the first ones the build produced.
  const withHeader = views.find((v) => v.header);
  if (withHeader) view.header = withHeader.header;
  const withBadges = views.find((v) => Array.isArray(v.badges) && v.badges.length);
  if (withBadges) view.badges = withBadges.badges;
  return view;
};

function defineDashboardStrategy(name, { domain, title, icon, build, strings, description }) {
  /* Shared by both strategy flavours: everything up to the finished view list. */
  const buildViews = async (config, hass) => {
    const t = translator(strings || {}, hass);
    let registry;
    try {
      registry = await loadRegistry(hass);
    } catch (err) {
      // Registry unreachable: render a readable message rather than
      // letting the dashboard fail with a blank screen.
      return [{ title: title, cards: [emptyNotice(`\u26a0\ufe0f ${err}`)] }];
    }
    const domainEntries = entriesOfDomain(registry.entities, domain);
    if (!domainEntries.length) {
      return [{ title: title, icon, cards: [emptyNotice(t("not_configured"))] }];
    }
    const views = await build({
      hass,
      config,
      t,
      domain,
      entities: domainEntries,
      devices: registry.devices,
      allEntities: registry.entities,
      helpers: { heading, grid, tile, mapCard, emptyNotice, bySuffix, groupByDevice, deviceName },
    });
    return applyViewOptions(views, config);
  };

  class Strategy extends HTMLElement {
    static async generate(config, hass) {
      const views = await buildViews(config, hass);
      return { title: (config && config.title) || title, views };
    }
  }

  /* The view flavour: fills a single view of a dashboard the user built
   * themselves, so adjusting the layout no longer requires "take control". */
  class ViewStrategy extends HTMLElement {
    static async generate(config, hass) {
      const views = await buildViews(config, hass);
      return flattenToView(views, (config && config.title) || title, icon, config);
    }
  }

  // getCreateSuggestions lets Home Assistant offer sensible defaults when the
  // strategy is picked from the "new dashboard" dialog.
  Strategy.getCreateSuggestions = () => ({ title, icon });

  customElements.define(`ll-strategy-dashboard-${name}`, Strategy);
  customElements.define(`ll-strategy-view-${name}`, ViewStrategy);

  // Announce the strategy to the frontend so it appears in the dashboard
  // creation dialog instead of having to be typed into the raw editor.
  window.customStrategies = window.customStrategies || [];
  if (!window.customStrategies.some((s) => s.type === name)) {
    window.customStrategies.push({
      type: name,
      strategyType: "dashboard",
      name: title,
      description: description || "",
    });
  }
  return Strategy;
}


/* =====================================================================
 * Dashboard strategy: Swiss Waters
 * =====================================================================
 * Generates the dashboard in the browser at render time. Versions up to
 * 1.2.0 created a "Swiss Waters" dashboard in the user's Lovelace storage;
 * 1.3.0 removed that without a replacement. This strategy fills the gap:
 * the same content — the station map and the bathing sites — plus a view
 * of the monitoring stations, generated fresh on every load with nothing
 * written into the user's configuration.
 *
 * It also keeps itself current: adding or removing a station or bathing
 * site changes the dashboard on the next load, with no leftovers when an
 * entry is deleted.
 *
 * Usage — create an empty dashboard, open the raw configuration editor and
 * replace its content with:
 *
 *     strategy:
 *       type: custom:swiss-waters
 *     views: []
 * ===================================================================== */

const SW_STRINGS = {
  en: {
    map: "Map",
    stations: "Stations",
    bathing: "Bathing sites",
    nothing_to_show:
      "### Nothing to show yet\n\nSwiss Waters is set up, but none of its stations or bathing sites has a visible sensor. Check the integration's devices under **Settings → Devices & services**.",
    not_configured:
      "### Swiss Waters is not set up yet\n\nAdd the integration under **Settings → Devices & services** first. This dashboard then fills itself — there is nothing to configure here.",
  },
  de: {
    map: "Karte",
    stations: "Messstationen",
    bathing: "Badestellen",
    nothing_to_show:
      "### Noch nichts anzuzeigen\n\nSwiss Waters ist eingerichtet, aber keine Messstation und keine Badestelle hat einen sichtbaren Sensor. Prüfe die Geräte der Integration unter **Einstellungen → Geräte & Dienste**.",
    not_configured:
      "### Swiss Waters ist noch nicht eingerichtet\n\nFüge die Integration zuerst unter **Einstellungen → Geräte & Dienste** hinzu. Dieses Dashboard füllt sich danach von selbst — hier ist nichts einzustellen.",
  },
  fr: {
    map: "Carte",
    stations: "Stations de mesure",
    bathing: "Sites de baignade",
    nothing_to_show:
      "### Rien à afficher pour l'instant\n\nSwiss Waters est configuré, mais aucune station de mesure ni aucun site de baignade n'a de capteur visible. Vérifiez les appareils de l'intégration sous **Paramètres → Appareils et services**.",
    not_configured:
      "### Swiss Waters n'est pas encore configuré\n\nAjoutez d'abord l'intégration sous **Paramètres → Appareils et services**. Ce tableau de bord se remplit ensuite tout seul.",
  },
  it: {
    map: "Mappa",
    stations: "Stazioni di misurazione",
    bathing: "Zone di balneazione",
    nothing_to_show:
      "### Ancora niente da mostrare\n\nSwiss Waters è configurato, ma nessuna stazione di misurazione e nessuna zona di balneazione ha un sensore visibile. Controlla i dispositivi dell'integrazione in **Impostazioni → Dispositivi e servizi**.",
    not_configured:
      "### Swiss Waters non è ancora configurato\n\nAggiungi prima l'integrazione in **Impostazioni → Dispositivi e servizi**. Questa dashboard si riempie poi da sola.",
  },
};

/* unique_id suffixes of the sensor platform, in display order. A monitoring
 * station's sensors are `<entry_id>_<station_id>_<measure>`, a bathing
 * site's `<entry_id>_<site_id>_<measure>`; the measure decides which view a
 * device belongs to. "water_temperature" is listed before "temperature" on
 * purpose: it ends with the same characters, and the first match wins.
 * (The geo_location markers use `swiss_waters_<entry_id>_<station_id>` and
 * are excluded by their entity_id before this lookup runs.) */
const SW_MEASURES = [
  ["bathing", "water_temperature"],
  ["bathing", "quality"],
  ["bathing", "last_sample"],
  ["station", "temperature"],
  ["station", "water_level"],
  ["station", "discharge"],
  ["station", "danger_level"],
];

/* Classify one registry entry. Unknown suffixes get no kind and sort after
 * the known measures, so a sensor added by a later version still shows up
 * instead of silently disappearing from its device's section. */
const SW_measureOf = (entry) => {
  const uid = typeof entry.unique_id === "string" ? entry.unique_id : "";
  const order = SW_MEASURES.findIndex(([, key]) => uid.endsWith(`_${key}`));
  return order < 0
    ? { kind: null, order: SW_MEASURES.length }
    : { kind: SW_MEASURES[order][0], order };
};

defineDashboardStrategy("swiss-waters", {
  domain: "swiss_waters",
  title: "Swiss Waters",
  icon: "mdi:waves",
  description:
    "Map of the monitoring stations plus one section per station and per bathing site, generated live from the integration.",
  strings: SW_STRINGS,

  async build({ t, domain, entities, devices, helpers }) {
    const { heading, grid, tile, mapCard, emptyNotice, groupByDevice, deviceName } = helpers;
    const views = [];

    // --- Map ----------------------------------------------------------
    // Only monitoring stations have markers; a setup with bathing sites
    // alone has none, and an empty map would just look broken.
    const hasMarkers = entities.some((e) => e.entity_id.startsWith("geo_location."));
    if (hasMarkers) {
      views.push({
        title: t("map"),
        path: "map",
        icon: "mdi:map",
        type: "panel",
        cards: [mapCard(domain, { zoom: 9, rows: 12, labelAttribute: "temperature" })],
      });
    }

    // --- One section per device ---------------------------------------
    // Every monitoring station and every bathing site is its own device.
    // Which view a device lands in follows from its sensors' unique_id
    // suffixes, so a user-renamed entity_id keeps working.
    const stationSections = [];
    const bathingSections = [];
    const groups = groupByDevice(
      entities.filter((e) => !e.hidden_by && !e.entity_id.startsWith("geo_location.")),
      devices
    );
    // groupByDevice sorts by name only. Two devices may share one — a
    // favourite bathing site that also lies inside a radius search — so
    // break ties by device id to keep the order stable between loads.
    groups.sort(
      (a, b) =>
        deviceName(a.device).localeCompare(deviceName(b.device)) ||
        a.device.id.localeCompare(b.device.id)
    );
    for (const group of groups) {
      const items = group.entities
        .map((e) => ({ entityId: e.entity_id, ...SW_measureOf(e) }))
        .sort((a, b) => a.order - b.order || a.entityId.localeCompare(b.entityId));
      // Known measures sort first, so the first item decides the kind. A
      // device without any known measure is skipped rather than guessed.
      const kind = items[0].kind;
      if (!kind) continue;
      const cards = [
        heading(deviceName(group.device), kind === "bathing" ? "mdi:swim" : "mdi:waves"),
        ...items.map((item) => tile(item.entityId, { grid_options: { columns: 6 } })),
      ];
      (kind === "bathing" ? bathingSections : stationSections).push(grid(cards));
    }

    if (stationSections.length) {
      views.push({
        title: t("stations"),
        path: "stations",
        icon: "mdi:waves",
        type: "sections",
        max_columns: 2,
        sections: stationSections,
      });
    }
    if (bathingSections.length) {
      views.push({
        title: t("bathing"),
        path: "bathing",
        icon: "mdi:swim",
        type: "sections",
        max_columns: 2,
        sections: bathingSections,
      });
    }

    // The integration is set up (the core checked that), yet nothing is
    // left to render — every sensor hidden, for instance. Say so instead
    // of showing a blank page.
    if (!views.length) {
      views.push({ title: t("stations"), cards: [emptyNotice(t("nothing_to_show"))] });
    }

    return views;
  },
});
})();
