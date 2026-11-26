/**
 * Chart.js lifecycle and result plotting for traffic jobs.
 *
 * The queue and the history panel both plot results through the shared
 * registry below. All result parsing lives in `traffic_plots_model.js`; this
 * module only builds Chart.js configuration, owns live chart instances, and
 * opens the results dialog with the established markup.
 */
import { byId } from "./dom.js";
import { openModal } from "./results_modal.js?v=1";
import {
  buildHping3Series,
  buildIperf3Series,
  formatTick,
  hping3MetricRows,
  iperf3MetricRows,
  metricsHtml,
  pingMetricRows,
} from "./traffic_plots_model.js?v=1";

const CHARTS_UNAVAILABLE =
  '<p class="muted">Charts are unavailable because the Chart.js CDN did not load.</p>';
const FLOW_COLORS = [
  "#ef4444",
  "#22c55e",
  "#eab308",
  "#a78bfa",
  "#f472b6",
  "#60a5fa",
  "#f97316",
  "#84cc16",
];
const activeCharts = [];
let plotGeneration = 0;

/**
 * Create and track one Chart.js instance.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {object} config
 * @returns {object}
 */
export function createChart(canvas, config) {
  const chart = new Chart(canvas, config);
  activeCharts.push(chart);
  return chart;
}

/** Destroy every live chart and invalidate pending plot callbacks. */
export function destroyCharts() {
  plotGeneration += 1;
  for (const chart of activeCharts.splice(0)) {
    try {
      chart.destroy();
    } catch {
      /* a detached chart is already harmless */
    }
  }
}

/**
 * Generation token used to discard chart callbacks scheduled before a modal
 * re-open or close.
 *
 * @returns {number}
 */
export function currentPlotGeneration() {
  return plotGeneration;
}

/**
 * One Chart.js line-chart options block for every result chart.
 *
 * @param {string|null|undefined} yTitle - Y-axis title, omitted when nullish.
 * @param {{
 *   beginAtZero?: boolean,
 *   logarithmic?: boolean,
 *   xTitle?: string,
 *   xTickFormatter?: ((value: unknown) => unknown)|null,
 *   legend?: boolean,
 * }} [overrides]
 * @returns {object}
 */
export function lineChartOptions(yTitle, overrides = {}) {
  const {
    beginAtZero = true,
    logarithmic = false,
    xTitle = "Time (s)",
    xTickFormatter = null,
    legend = true,
  } = overrides;
  const xScale = {
    title: { display: true, text: xTitle },
    grid: { color: "#1e2937" },
  };
  if (xTickFormatter) xScale.ticks = { callback: xTickFormatter };
  const yScale = {};
  if (beginAtZero) yScale.beginAtZero = true;
  if (logarithmic) yScale.type = "logarithmic";
  if (yTitle !== null && yTitle !== undefined) {
    yScale.title = { display: true, text: yTitle };
  }
  yScale.grid = { color: "#1e2937" };
  return {
    responsive: true,
    animation: false,
    plugins: { legend: { display: legend } },
    scales: { x: xScale, y: yScale },
  };
}

function flowDatasets(values, prefix) {
  return values.map((series, index) => ({
    label: `${prefix} ${index + 1}`,
    data: series,
    borderColor: FLOW_COLORS[index % FLOW_COLORS.length],
    tension: 0.2,
    borderDash: [6, 4],
    pointRadius: 0,
  }));
}

function plotLine(canvasId, labels, datasets, options) {
  const canvas = byId(canvasId);
  if (!canvas || !window.Chart) return null;
  return createChart(canvas, {
    type: "line",
    data: { labels, datasets },
    options,
  });
}

/**
 * Plot an iperf3 result payload in the results dialog.
 *
 * @param {{kind?: string, payload: object, results: object}} item
 */
export function plotIperf3(item) {
  const result = item.results;
  const series = buildIperf3Series(result);
  const { isTcp, isUdp, streamCount } = series;
  const metricsMarkup = metricsHtml(iperf3MetricRows(result));

  const chartsMarkup =
    (window.Chart ? "" : CHARTS_UNAVAILABLE) +
    '<div class="chart-grid">' +
    '<div class="chart-container"><canvas id="chart-main-1"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-aux"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-main-2"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-cum"></canvas></div>' +
    (isTcp
      ? '<div class="chart-container"><canvas id="chart-tput-tcp"></canvas></div>'
      : "") +
    "</div>";

  openModal(
    `iperf3 Results - ${item.payload.src} -> ${item.payload.dst}`,
    metricsMarkup + chartsMarkup,
  );

  const generation = currentPlotGeneration();
  requestAnimationFrame(() => {
    if (generation !== currentPlotGeneration()) return;

    const axesPrimary = lineChartOptions(isTcp ? "KB" : "Mbps", {
      xTickFormatter: formatTick,
    });
    const axesAux = lineChartOptions(isUdp ? "%" : "Count", {
      xTickFormatter: formatTick,
    });
    const axesRtt = lineChartOptions("ms", { xTickFormatter: formatTick });
    const axesCumulative = lineChartOptions("Mbit", {
      xTickFormatter: formatTick,
    });
    const axesJitter = lineChartOptions("Jitter (ms, log)", {
      beginAtZero: false,
      logarithmic: true,
      xTickFormatter: formatTick,
    });
    const axesThroughput = lineChartOptions("Mbps", {
      xTickFormatter: formatTick,
    });

    const mainChart = byId("chart-main-1");
    if (mainChart && window.Chart) {
      const base = isTcp
        ? {
            label: "CWND (KB)",
            data: series.cwnd,
            borderColor: "#3da9fc",
            tension: 0.2,
          }
        : {
            label: "Throughput (Mbps)",
            data: series.throughput,
            borderColor: "#3da9fc",
            tension: 0.2,
          };
      const overlays = isTcp
        ? flowDatasets(series.perCwnd, "Flow CWND")
        : flowDatasets(series.perThroughput, "Flow Mbps");
      createChart(mainChart, {
        type: "line",
        data: {
          labels: series.times,
          datasets: [base].concat(streamCount > 1 ? overlays : []),
        },
        options: axesPrimary,
      });
    }

    const auxChart = byId("chart-aux");
    if (auxChart && window.Chart) {
      const overlays = flowDatasets(
        series.perAux,
        isUdp ? "Flow Loss %" : "Flow Retrans",
      );
      createChart(auxChart, {
        type: "line",
        data: {
          labels: series.times,
          datasets: [
            {
              label: isUdp ? "Loss %" : "Retrans",
              data: series.aux,
              borderColor: "#f59e0b",
              tension: 0.2,
            },
          ].concat(streamCount > 1 ? overlays : []),
        },
        options: axesAux,
      });
    }

    const secondaryChart = byId("chart-main-2");
    if (secondaryChart && window.Chart) {
      if (isTcp) {
        const overlays = flowDatasets(series.perRtt, "Flow RTT");
        createChart(secondaryChart, {
          type: "line",
          data: {
            labels: series.times,
            datasets: [
              {
                label: "RTT (ms)",
                data: series.rtt,
                borderColor: "#10b981",
                tension: 0.2,
              },
            ].concat(streamCount > 1 ? overlays : []),
          },
          options: axesRtt,
        });
      } else {
        const overlays = flowDatasets(series.perJitter, "Flow Jitter");
        createChart(secondaryChart, {
          type: "line",
          data: {
            labels: series.times,
            datasets: [
              {
                label: "Jitter (ms)",
                data: series.jitter,
                borderColor: "#22c55e",
                tension: 0.2,
              },
            ].concat(streamCount > 1 ? overlays : []),
          },
          options: axesJitter,
        });
      }
    }

    const cumulativeChart = byId("chart-cum");
    if (cumulativeChart && window.Chart) {
      createChart(cumulativeChart, {
        type: "line",
        data: {
          labels: series.times,
          datasets: [
            {
              label: "Cumulative Bits (Mbit)",
              data: series.cumulativeBits,
              borderColor: "#a78bfa",
              tension: 0.2,
            },
          ],
        },
        options: axesCumulative,
      });
    }

    if (isTcp) {
      const throughputChart = byId("chart-tput-tcp");
      if (throughputChart && window.Chart) {
        const overlays = flowDatasets(series.perThroughput, "Flow Mbps");
        createChart(throughputChart, {
          type: "line",
          data: {
            labels: series.times,
            datasets: [
              {
                label: "Throughput (Mbps)",
                data: series.throughput,
                borderColor: "#3da9fc",
                tension: 0.2,
              },
            ].concat(streamCount > 1 ? overlays : []),
          },
          options: axesThroughput,
        });
      }
    }
  });
}

/**
 * Plot ping results in the results dialog.
 *
 * @param {{payload: object, results: object}} item
 */
export function plotPing(item) {
  openModal(
    `Ping Results - ${item.payload.src} -> ${item.payload.dst}`,
    metricsHtml(pingMetricRows(item.results)),
  );
}

/**
 * Plot hping3 results in the results dialog.
 *
 * @param {{payload: object, results: object}} item
 */
export function plotHping3(item) {
  const result = item.results;
  const series = buildHping3Series(result);
  const chartsMarkup =
    (window.Chart ? "" : CHARTS_UNAVAILABLE) +
    '<div class="chart-grid">' +
    '<div class="chart-container"><canvas id="chart-hping-rtt"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-hping-cum"></canvas></div>' +
    "</div>";

  openModal(
    `hping3 Results - ${item.payload.src} -> ${item.payload.dst}`,
    metricsHtml(hping3MetricRows(result)) + chartsMarkup,
  );

  const generation = currentPlotGeneration();
  requestAnimationFrame(() => {
    if (generation !== currentPlotGeneration()) return;
    plotLine(
      "chart-hping-rtt",
      series.labels,
      [
        {
          label: "RTT (ms)",
          data: series.rtt,
          borderColor: "#3da9fc",
          tension: 0.2,
          pointRadius: 2,
        },
      ],
      lineChartOptions(null, { beginAtZero: false }),
    );
    plotLine(
      "chart-hping-cum",
      series.labels,
      [
        {
          label: "Cumulative Mbit",
          data: series.cumulativeMbit,
          borderColor: "#22c55e",
          tension: 0.2,
          pointRadius: 2,
        },
      ],
      lineChartOptions(null, { beginAtZero: false }),
    );
  });
}

const PLOTTERS = {
  iperf3: plotIperf3,
  ping: plotPing,
  hping3: plotHping3,
};

/**
 * Look up the plotter for a traffic kind.
 *
 * @param {string} kind
 * @returns {((item: object) => void)|null}
 */
export function getPlotter(kind) {
  return PLOTTERS[kind] || null;
}

/**
 * Plot one result payload through the shared registry.
 *
 * @param {string} kind
 * @param {{payload: object, results: object}} item
 * @returns {boolean} Whether a plotter existed for the kind.
 */
export function plotResult(kind, item) {
  const plot = getPlotter(kind);
  if (!plot) return false;
  plot(item);
  return true;
}
