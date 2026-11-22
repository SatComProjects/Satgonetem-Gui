import { describe, expect, it } from "vitest";

import {
  HISTORY_VERSION,
  MAX_HISTORY_RECORDS,
  addHistoryRecord,
  buildHistoryRecord,
  compactResults,
  compareRuns,
  historySummaryText,
  historyToCsv,
  historyToJson,
  normalizeHistory,
  removeHistoryRecord,
  summaryMetrics,
} from "../satgonetem_gui/static/history_model.js";

const iperfResults = {
  protocol: "TCP",
  avg_throughput_mbps: 120.5,
  max_throughput_mbps: 150,
  min_throughput_mbps: 90,
  total_retransmits: 4,
  avg_rtt_ms: 18.2,
  intervals: [
    { sum: { seconds: 1, bits_per_second: 100_000_000, bytes: 12_500_000 } },
    { sum: { seconds: 1, bits_per_second: 150_000_000, bytes: 18_750_000 } },
  ],
};

function pingRecord(id = "run-1", jobId = "j1") {
  return buildHistoryRecord({
    id,
    jobId,
    kind: "ping",
    label: "ping Sat0 -> Gnd100",
    payload: { src: "Sat0", dst: "Gnd100" },
    results: {
      packets_received: 9,
      packets_transmitted: 10,
      packet_loss_percent: 10,
      rtt_avg_ms: 24.5,
      rtt_min_ms: 21,
      rtt_max_ms: 30,
    },
    startedAt: 1_000,
    finishedAt: 3_000,
    projectName: "Demo",
  });
}

function hpingRecord(id = "run-2", jobId = "j2") {
  return buildHistoryRecord({
    id,
    jobId,
    kind: "hping3",
    label: "hping3 Sat1 -> Gnd100",
    payload: { src: "Sat1", dst: "Gnd100" },
    results: {
      packets_received: 8,
      packets_transmitted: 10,
      packet_loss_percent: 20,
      rtt_avg_ms: 30,
      rtt_min_ms: 20,
      rtt_max_ms: 50,
      seq: [1, 2, 3],
      rtt_ms: [20, 30, 50],
    },
    startedAt: 2_000,
    finishedAt: 5_000,
    projectName: "Demo",
  });
}

describe("history compaction", () => {
  it("truncates long iperf3 interval arrays", () => {
    const intervals = Array.from({ length: 600 }, (_value, index) => ({
      sum: { seconds: 1, bits_per_second: index },
    }));

    const compact = compactResults("iperf3", { intervals }, 100);

    expect(compact.intervals).toHaveLength(100);
    expect(compact.intervals_truncated).toBe(true);
  });

  it("returns null for a missing result payload", () => {
    expect(compactResults("iperf3", null)).toBeNull();
    expect(compactResults("ping", undefined)).toBeNull();
  });
});

describe("history summary", () => {
  it("summarizes TCP and ping results", () => {
    expect(summaryMetrics("iperf3", iperfResults).map((entry) => entry.label)).toEqual([
      "Avg throughput",
      "Max throughput",
      "Min throughput",
      "Retransmits",
      "Avg RTT",
    ]);
    expect(
      summaryMetrics("ping", {
        packets_received: 9,
        packets_transmitted: 10,
        packet_loss_percent: 10,
        rtt_avg_ms: 24.5,
      }).map((entry) => entry.label),
    ).toContain("Loss");
  });

  it("formats a short history row", () => {
    expect(historySummaryText(pingRecord())).toBe("24.5 ms \u00b7 10 %");
  });
});

describe("history records", () => {
  it("builds a record with duration, project, and summary", () => {
    const record = pingRecord();

    expect(record.id).toBe("run-1");
    expect(record.job_id).toBe("j1");
    expect(record.duration_ms).toBe(2_000);
    expect(record.project_name).toBe("Demo");
    expect(record.summary.length).toBeGreaterThan(0);
    expect(record.results.packets_received).toBe(9);
  });

  it("disables an existing job record instead of duplicating it", () => {
    const first = pingRecord("run-1", "j1");
    const replacement = { ...pingRecord("run-2", "j1"), label: "replacement" };
    const history = addHistoryRecord(
      { version: HISTORY_VERSION, records: [first] },
      replacement,
    );

    expect(history.records).toHaveLength(1);
    expect(history.records[0].label).toBe("replacement");
  });

  it("keeps the newest records first and caps the ledger", () => {
    let history = normalizeHistory(null);
    for (let index = 0; index < MAX_HISTORY_RECORDS + 5; index += 1) {
      history = addHistoryRecord(history, {
        ...pingRecord(`run-${index}`, `j${index}`),
        recorded_at: new Date(10_000 + index).toISOString(),
      });
    }

    expect(history.records).toHaveLength(MAX_HISTORY_RECORDS);
    expect(history.records[0].id).toBe(`run-${MAX_HISTORY_RECORDS + 4}`);
  });

  it("normalizes malformed records defensively", () => {
    const history = normalizeHistory({
      version: HISTORY_VERSION,
      records: [
        pingRecord(),
        { id: "bad", kind: "ping" },
        null,
        { id: "bad-2", kind: "ping", recorded_at: "not-a-date" },
      ],
    });

    expect(history.records).toHaveLength(1);
    expect(history.records[0].id).toBe("run-1");
  });

  it("removes one record by id", () => {
    const history = addHistoryRecord(
      { version: HISTORY_VERSION, records: [pingRecord()] },
      hpingRecord(),
    );

    const reduced = removeHistoryRecord(history, "run-1");

    expect(reduced.records.map((record) => record.id)).toEqual(["run-2"]);
  });
});

describe("history export", () => {
  it("escapes CSV values and includes a stable header", () => {
    const record = {
      ...pingRecord(),
      label: 'ping "quoted", line\nbreak',
    };
    const csv = historyToCsv({ version: HISTORY_VERSION, records: [record] });
    const [header] = csv.split("\n");

    expect(header).toContain("recorded_at,kind,label,src,dst");
    expect(csv).toContain('"ping ""quoted"", line\nbreak"');
    expect(csv).toContain("Sat0,Gnd100,Demo");
  });

  it("exports a versioned JSON envelope", () => {
    const json = historyToJson(
      { version: HISTORY_VERSION, records: [pingRecord()] },
      5_000,
    );
    const parsed = JSON.parse(json);

    expect(parsed.version).toBe(HISTORY_VERSION);
    expect(parsed.exported_at).toBe("1970-01-01T00:00:05.000Z");
    expect(parsed.records).toHaveLength(1);
  });
});

describe("run comparison", () => {
  it("builds summary rows with deltas for same-kind runs", () => {
    const first = pingRecord("run-1", "j1");
    const second = {
      ...pingRecord("run-2", "j2"),
      summary: summaryMetrics("ping", {
        packet_loss_percent: 0,
        rtt_avg_ms: 20,
      }),
    };

    const comparison = compareRuns(first, second);
    const loss = comparison.rows.find((row) => row.label === "Loss");

    expect(comparison.sameKind).toBe(true);
    expect(loss.first).toBe(10);
    expect(loss.second).toBe(0);
    expect(loss.delta).toBe(-10);
  });

  it("overlays the primary iperf3 throughput series", () => {
    const first = buildHistoryRecord({
      id: "a",
      jobId: "ja",
      kind: "iperf3",
      label: "iperf3 a",
      payload: { src: "Gnd100", dst: "Gnd101" },
      results: iperfResults,
      finishedAt: 1_000,
    });
    const second = buildHistoryRecord({
      id: "b",
      jobId: "jb",
      kind: "iperf3",
      label: "iperf3 b",
      payload: { src: "Gnd100", dst: "Gnd101" },
      results: iperfResults,
      finishedAt: 2_000,
    });

    const comparison = compareRuns(first, second);

    expect(comparison.series.label).toBe("Throughput (Mbps)");
    expect(comparison.series.first).toEqual([100, 150]);
    expect(comparison.series.second).toEqual([100, 150]);
  });

  it("does not overlay series for different kinds", () => {
    const comparison = compareRuns(pingRecord(), hpingRecord());

    expect(comparison.sameKind).toBe(false);
    expect(comparison.series).toBeNull();
  });
});
