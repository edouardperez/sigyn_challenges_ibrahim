"use client";

import type { Toolkit } from "@assistant-ui/react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { StatsDisplay } from "@/components/tool-ui/stats-display";
import { Chart } from "@/components/tool-ui/chart";
import { DataTable } from "@/components/tool-ui/data-table";
import { WaterfallCard } from "@/components/tool-ui/waterfall-card";
import { SectorGauge } from "@/components/tool-ui/sector-gauge";

// ── metric_card ─────────────────────────────────────────────────────────────
// Backend block: { label, value, unit, status }
// Maps to StatsDisplay with a single stat item.

type MetricCardBlock = {
  label?: string;
  value?: number | string;
  unit?: string;
  status?: "healthy" | "warning" | "critical";
};

const statusTone: Record<string, string> = {
  healthy: "text-emerald-600",
  warning: "text-amber-600",
  critical: "text-rose-600",
};

function MetricCardRenderer({ result }: { result: unknown }) {
  const b = result as MetricCardBlock;
  if (!b || b.value == null) return null;

  const isEur = b.unit === "EUR";
  const isPct = b.unit === "%";

  return (
    <div className={b.status ? statusTone[b.status] ?? "" : ""}>
      <StatsDisplay
        id={`mc-${b.label}`}
        stats={[
          {
            key: "value",
            label: b.label ?? "Valeur",
            value: typeof b.value === "number" ? b.value : parseFloat(String(b.value)),
            format: isEur
              ? { kind: "currency", currency: "EUR", decimals: 0 }
              : isPct
              ? { kind: "percent", decimals: 1, basis: "unit" }
              : { kind: "number", decimals: 2 },
          },
        ]}
      />
    </div>
  );
}

// ── table ────────────────────────────────────────────────────────────────────
// Backend block: { title, columns: string[], rows: any[][] }

type TableBlock = {
  title?: string;
  columns?: string[];
  rows?: unknown[][];
};

function TableRenderer({ result }: { result: unknown }) {
  const b = result as TableBlock;
  if (!b?.columns?.length || !b?.rows?.length) return null;

  const cols = b.columns.map((col, i) => ({
    key: `col${i}`,
    label: col,
  }));

  const data = b.rows.map((row) => {
    const obj: Record<string, unknown> = {};
    (row as unknown[]).forEach((cell, i) => {
      obj[`col${i}`] = cell;
    });
    return obj as Record<string, string | number | boolean | null>;
  });

  return <DataTable id={`tbl-${b.title ?? "table"}`} columns={cols} data={data} maxHeight="320px" />;
}

// ── chart ────────────────────────────────────────────────────────────────────
// Backend block: { label, data: [{period, value}] }
// Multi-series: { label, chart_type, xKey, series: [{key, label}], data: [{period, seriesA: n, seriesB: n}] }

type ChartBlock = {
  label?: string;
  rubrique_key?: string;
  chart_type?: "line" | "bar";
  xKey?: string;
  series?: Array<{ key: string; label: string; color?: string }>;
  data?: Array<Record<string, unknown>>;
};

function ChartRenderer({ result }: { result: unknown }) {
  const b = result as ChartBlock;
  if (!b?.data?.length) return null;

  // Multi-series format: explicit xKey + series array
  if (b.xKey && b.series?.length) {
    const numericData = b.data.map((row) => {
      const out: Record<string, unknown> = { [b.xKey!]: row[b.xKey!] };
      for (const s of b.series!) {
        out[s.key] = Number(row[s.key]) || 0;
      }
      return out;
    });

    return (
      <Chart
        id={`chart-${b.label ?? "comparison"}`}
        type={b.chart_type ?? "line"}
        title={b.label}
        data={numericData}
        xKey={b.xKey}
        series={b.series}
        showGrid
        showLegend
      />
    );
  }

  // Legacy single-series format (auto-detect)
  const sample = b.data[0];
  const xKey = Object.keys(sample).find((k) => typeof sample[k] === "string") ?? "period";
  const valueKey = Object.keys(sample).find((k) => typeof sample[k] === "number") ?? "value";

  const numericData = b.data.map((row) => ({
    ...row,
    [valueKey]: Number(row[valueKey]) || 0,
  }));

  return (
    <Chart
      id={`chart-${b.label ?? b.rubrique_key ?? "chart"}`}
      type={b.chart_type ?? "bar"}
      title={b.label}
      data={numericData}
      xKey={xKey}
      series={[{ key: valueKey, label: b.label ?? valueKey }]}
      showGrid
    />
  );
}

// ── waterfall_card ───────────────────────────────────────────────────────────
function WaterfallRenderer({ result }: { result: unknown }) {
  const b = result as { title?: string; sections?: unknown[] };
  return <WaterfallCard title={b?.title} sections={b?.sections as never} />;
}

// ── sector_gauge ─────────────────────────────────────────────────────────────
function SectorGaugeRenderer({ result }: { result: unknown }) {
  const b = result as {
    label?: string;
    value?: number;
    q1?: number;
    mediane?: number;
    q3?: number;
    position?: string;
    unit?: string;
  };
  return <SectorGauge {...b} />;
}

// ── alert ────────────────────────────────────────────────────────────────────
const alertVariant: Record<string, "default" | "destructive"> = {
  critical: "destructive",
  warning: "default",
  info: "default",
};

function AlertRenderer({ result }: { result: unknown }) {
  const b = result as { level?: string; message?: string };
  if (!b?.message) return null;
  return (
    <Alert variant={alertVariant[b.level ?? "info"] ?? "default"}>
      <AlertDescription>{b.message}</AlertDescription>
    </Alert>
  );
}

// ── text ─────────────────────────────────────────────────────────────────────
function TextRenderer({ result }: { result: unknown }) {
  const b = result as { content?: string };
  if (!b?.content) return null;
  return <p className="text-sm leading-relaxed text-muted-foreground">{b.content}</p>;
}

// ── Toolkit ──────────────────────────────────────────────────────────────────
export const toolkit: Toolkit = {
  show_metric_card: {
    type: "backend",
    render: ({ result }) => <MetricCardRenderer result={result} />,
  },
  show_table: {
    type: "backend",
    render: ({ result }) => <TableRenderer result={result} />,
  },
  show_chart: {
    type: "backend",
    render: ({ result }) => <ChartRenderer result={result} />,
  },
  show_waterfall_card: {
    type: "backend",
    render: ({ result }) => <WaterfallRenderer result={result} />,
  },
  show_sector_gauge: {
    type: "backend",
    render: ({ result }) => <SectorGaugeRenderer result={result} />,
  },
  show_alert: {
    type: "backend",
    render: ({ result }) => <AlertRenderer result={result} />,
  },
  show_text: {
    type: "backend",
    render: ({ result }) => <TextRenderer result={result} />,
  },
};
