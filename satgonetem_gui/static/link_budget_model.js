/** Pure formatting helpers for the link-budget workbench. */

function number(value) {
  if (value === null || value === undefined || value === "") return NaN;
  return Number(value);
}

export function formatDb(value, unit = "dB", digits = 2) {
  const numeric = number(value);
  if (!Number.isFinite(numeric)) return "\u2014";
  return `${numeric.toFixed(digits)} ${unit}`;
}

export function formatCapacity(kbps) {
  const numeric = number(kbps);
  if (!Number.isFinite(numeric)) return "\u2014";
  if (numeric <= 0) return "0 kbps";
  const bps = numeric * 1000;
  if (bps >= 1e9) return `${(bps / 1e9).toFixed(1)} Gbps`;
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)} Mbps`;
  if (bps >= 1e3) return `${(bps / 1e3).toFixed(1)} kbps`;
  return `${Math.round(bps)} bps`;
}

export function strategyLabel(strategy) {
  if (strategy === "shannon") return "Shannon";
  if (strategy === "modcod") return "MODCOD";
  return strategy || "\u2014";
}

export function directionLabel(direction) {
  if (direction === "downlink") return "Downlink";
  if (direction === "uplink") return "Uplink";
  return direction || "\u2014";
}

function formattedNumber(value, unit) {
  const numeric = number(value);
  if (!Number.isFinite(numeric)) return "\u2014";
  return `${new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
  }).format(numeric)} ${unit}`;
}

export function budgetSummary(result) {
  if (!result || typeof result !== "object") return "\u2014";
  return [
    directionLabel(result.direction),
    formattedNumber(result.frequency_ghz, "GHz"),
    formattedNumber(result.bandwidth_mhz, "MHz"),
    formattedNumber(result.distance_km, "km"),
    strategyLabel(result.strategy),
  ].join(" \u00b7 ");
}

export function budgetRows(result) {
  if (!result || typeof result !== "object") return [];
  return [
    { label: "Capacity", value: formatCapacity(result.capacity_kbps) },
    { label: "EIRP", value: formatDb(result.eirp_db, "dBW") },
    { label: "G/T", value: formatDb(result.g_over_t_db, "dB/K") },
    { label: "Free-space loss", value: formatDb(result.fspl_db) },
    {
      label: "Atmospheric loss",
      value: result.atmospheric_available
        ? formatDb(result.atmospheric_db)
        : "Unavailable (0 dB used)",
    },
    { label: "C/N\u2080", value: formatDb(result.cn0_dbhz, "dB-Hz") },
    { label: "C/N", value: formatDb(result.cn_db) },
  ];
}

export function atmosphereNote(result) {
  if (result?.atmospheric_available === false) {
    return "Atmospheric attenuation unavailable (optional ITU model missing); 0 dB was used.";
  }
  return "";
}
