/** Pure helpers for the connectivity-matrix page. */

/**
 * @param {number} nodeCount
 * @returns {number}
 */
export function pairCount(nodeCount) {
  const count = Number(nodeCount);
  if (!Number.isInteger(count) || count < 2) return 0;
  return count * (count - 1);
}

/**
 * @param {number|null|undefined} lossPercent
 * @param {boolean} reachable
 * @returns {"unreachable"|"loss-none"|"loss-low"|"loss-mid"|"loss-high"|"loss-full"}
 */
export function lossBucket(lossPercent, reachable) {
  if (!reachable) return "unreachable";
  const loss = Number(lossPercent);
  if (!Number.isFinite(loss) || loss <= 0) return "loss-none";
  if (loss < 25) return "loss-low";
  if (loss < 60) return "loss-mid";
  if (loss < 100) return "loss-high";
  return "loss-full";
}

/**
 * @param {number|null|undefined} lossPercent
 * @returns {string}
 */
export function formatLoss(lossPercent) {
  if (lossPercent === null || lossPercent === undefined) return "\u2014";
  const loss = Number(lossPercent);
  if (!Number.isFinite(loss)) return "\u2014";
  return `${Number(loss.toFixed(1))}%`;
}

/**
 * @param {number|null|undefined} rttMs
 * @returns {string}
 */
export function formatRtt(rttMs) {
  if (rttMs === null || rttMs === undefined) return "\u2014";
  const rtt = Number(rttMs);
  if (!Number.isFinite(rtt)) return "\u2014";
  return `${Number(rtt.toFixed(2))} ms`;
}

/**
 * @param {Array<object>} results
 * @returns {Map<string, object>}
 */
export function resultMap(results) {
  const map = new Map();
  for (const result of Array.isArray(results) ? results : []) {
    if (!result || !result.source || !result.destination) continue;
    map.set(`${result.source}\u0000${result.destination}`, result);
  }
  return map;
}

/**
 * @param {object|null|undefined} summary
 * @param {number|null|undefined} elapsedMs
 * @returns {string}
 */
export function summaryText(summary, elapsedMs) {
  if (!summary) return "";
  const pairs = Number(summary.pairs) || 0;
  const reachable = Number(summary.reachable) || 0;
  const unreachable = Number(summary.unreachable) || 0;
  const elapsed = Number(elapsedMs);
  const elapsedText = Number.isFinite(elapsed) ? ` \u00b7 ${(elapsed / 1000).toFixed(1)} s` : "";
  return (
    `${pairs} pair${pairs === 1 ? "" : "s"} \u00b7 ` +
    `${reachable} reachable \u00b7 ${unreachable} unreachable${elapsedText}`
  );
}
