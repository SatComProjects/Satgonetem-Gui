/** Pure helpers for the topology health card. */

function count(nodes) {
  const value = Number(nodes);
  return Number.isFinite(value) ? value : null;
}

export function healthSummary(health) {
  if (!health || typeof health !== "object") return "\u2014";
  const nodes = count(health.nodes);
  const links = count(health.links);
  const parts = [];
  if (nodes !== null) {
    parts.push(`${nodes} node${nodes === 1 ? "" : "s"}`);
  }
  if (links !== null) {
    parts.push(`${links} link${links === 1 ? "" : "s"}`);
  }
  const checks = Array.isArray(health.checks) ? health.checks : [];
  const warnings = checks.filter(
    (check) => check?.severity === "warning" && Number(check?.count) > 0,
  ).length;
  if (warnings > 0) {
    parts.push(`${warnings} warning${warnings === 1 ? "" : "s"}`);
  } else if (health.healthy) {
    parts.push("healthy");
  } else {
    parts.push("no warnings");
  }
  return parts.length ? parts.join(" \u00b7 ") : "\u2014";
}

export function severityLabel(severity) {
  if (severity === "warning") return "Warning";
  if (severity === "info") return "Info";
  return "Notice";
}

export function formatItemCount(value) {
  if (value === null || value === undefined || value === "") return "\u2014";
  const number = Number(value);
  if (!Number.isFinite(number)) return "\u2014";
  return `${number} item${number === 1 ? "" : "s"}`;
}

/** Non-empty findings with warnings before informational checks. */
export function nonEmptyChecks(checks) {
  if (!Array.isArray(checks)) return [];
  return checks
    .filter((check) => Number(check?.count) > 0)
    .sort((left, right) => {
      const leftRank = left?.severity === "warning" ? 0 : 1;
      const rightRank = right?.severity === "warning" ? 0 : 1;
      if (leftRank !== rightRank) return leftRank - rightRank;
      return String(left?.id || "").localeCompare(String(right?.id || ""));
    });
}
