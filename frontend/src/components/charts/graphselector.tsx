// GraphSelector.tsx
// Dashboard graph selector — chart type toggle + X/Y axis dropdowns + Recharts render
// Drop this into your dashboard CRM panel.
//
// Props:
//   data        : array of objects from your DB query result
//   availableCols: column names from the active connection's schema
//   title?      : panel title (default "Data Explorer")

import { useState, useMemo } from "react";
import {
  BarChart, Bar, LineChart, Line, ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

// ─── Types ────────────────────────────────────────────────────────────────────

type ChartType = "bar" | "line" | "scatter";

interface GraphSelectorProps {
  data: Record<string, unknown>[];
  availableCols: string[];
  title?: string;
  height?: number;
}

// ─── Chart type config ────────────────────────────────────────────────────────

const CHART_TYPES: { id: ChartType; label: string; icon: string }[] = [
  { id: "bar",     label: "Bar",     icon: "▐▌" },
  { id: "line",    label: "Line",    icon: "⟋"  },
  { id: "scatter", label: "Scatter", icon: "··" },
];

const ACCENT = "#7F77DD"; // c-purple-400
const ACCENT2 = "#1D9E75"; // c-teal-400

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isNumericCol(data: Record<string, unknown>[], col: string): boolean {
  const sample = data.slice(0, 20).map((r) => r[col]);
  return sample.some((v) => v !== null && v !== undefined && !isNaN(Number(v)));
}

function autoPickCols(
  data: Record<string, unknown>[],
  cols: string[]
): { xDefault: string; yDefault: string } {
  const numericCols = cols.filter((c) => isNumericCol(data, c));
  const nonNumericCols = cols.filter((c) => !isNumericCol(data, c));

  // For X: prefer a date or name/label column, else first column
  const xCandidates = [
    cols.find((c) => /date|time|month|year|period|name|label|category/i.test(c)),
    nonNumericCols[0],
    cols[0],
  ].filter(Boolean) as string[];

  // For Y: prefer a numeric column that isn't the X column
  const xPick = xCandidates[0] ?? cols[0];
  const yCandidates = numericCols.filter((c) => c !== xPick);

  return {
    xDefault: xPick,
    yDefault: yCandidates[0] ?? numericCols[0] ?? cols[1] ?? cols[0],
  };
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function GraphSelector({
  data,
  availableCols,
  title = "Data Explorer",
  height = 320,
}: GraphSelectorProps) {
  const { xDefault, yDefault } = useMemo(
    () => autoPickCols(data, availableCols),
    [data, availableCols]
  );

  const [chartType, setChartType] = useState<ChartType>("bar");
  const [xCol, setXCol] = useState(xDefault);
  const [yCol, setYCol] = useState(yDefault);
  const [limit, setLimit] = useState(50);

  // Prepare chart data — slice and coerce Y to number
  const chartData = useMemo(
    () =>
      data.slice(0, limit).map((row) => ({
        ...row,
        [xCol]: row[xCol] ?? "",
        [yCol]: Number(row[yCol]) || 0,
      })),
    [data, xCol, yCol, limit]
  );

  const numericCols = useMemo(
    () => availableCols.filter((c) => isNumericCol(data, c)),
    [data, availableCols]
  );

  // ── Render the chart ────────────────────────────────────────────────────────

  function renderChart() {
    const commonProps = {
      data: chartData,
      margin: { top: 8, right: 16, left: 0, bottom: 8 },
    };

    const axis = (
      <>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(127,119,221,0.12)" />
        <XAxis
          dataKey={xCol}
          tick={{ fontSize: 11, fill: "var(--color-text-secondary)" }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 11, fill: "var(--color-text-secondary)" }}
          tickLine={false}
          axisLine={false}
          width={48}
        />
        <Tooltip
          contentStyle={{
            background: "var(--color-background-primary)",
            border: "1px solid var(--color-border-secondary)",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </>
    );

    if (chartType === "bar") {
      return (
        <BarChart {...commonProps}>
          {axis}
          <Bar dataKey={yCol} fill={ACCENT} radius={[3, 3, 0, 0]} maxBarSize={40} />
        </BarChart>
      );
    }
    if (chartType === "line") {
      return (
        <LineChart {...commonProps}>
          {axis}
          <Line
            type="monotone"
            dataKey={yCol}
            stroke={ACCENT}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      );
    }
    // scatter
    return (
      <ScatterChart {...commonProps}>
        {axis}
        <Scatter name={`${xCol} vs ${yCol}`} data={chartData} fill={ACCENT2} opacity={0.7} />
      </ScatterChart>
    );
  }

  // ── UI ──────────────────────────────────────────────────────────────────────

  return (
    <div
      style={{
        background: "var(--color-background-primary)",
        border: "1px solid var(--color-border-tertiary)",
        borderRadius: 12,
        padding: "16px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <span style={{ fontWeight: 500, fontSize: 14, color: "var(--color-text-primary)" }}>
          {title}
        </span>
        {/* Chart type toggle */}
        <div style={{ display: "flex", gap: 4 }}>
          {CHART_TYPES.map(({ id, label, icon }) => (
            <button
              key={id}
              onClick={() => setChartType(id)}
              title={label}
              style={{
                padding: "4px 10px",
                fontSize: 12,
                borderRadius: 6,
                border: "1px solid",
                cursor: "pointer",
                borderColor: chartType === id ? ACCENT : "var(--color-border-secondary)",
                background: chartType === id ? `${ACCENT}18` : "transparent",
                color: chartType === id ? ACCENT : "var(--color-text-secondary)",
                fontWeight: chartType === id ? 500 : 400,
                transition: "all 0.15s",
              }}
            >
              {icon} {label}
            </button>
          ))}
        </div>
      </div>

      {/* Axis controls */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--color-text-secondary)" }}>
          X axis
          <select
            value={xCol}
            onChange={(e) => setXCol(e.target.value)}
            style={selectStyle}
          >
            {availableCols.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--color-text-secondary)" }}>
          Y axis
          <select
            value={yCol}
            onChange={(e) => setYCol(e.target.value)}
            style={selectStyle}
          >
            {numericCols.length > 0
              ? numericCols.map((c) => <option key={c} value={c}>{c}</option>)
              : availableCols.map((c) => <option key={c} value={c}>{c}</option>)
            }
          </select>
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--color-text-secondary)", marginLeft: "auto" }}>
          Rows
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            style={{ ...selectStyle, width: 72 }}
          >
            {[25, 50, 100, 500].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
      </div>

      {/* Chart */}
      {data.length === 0 ? (
        <div style={{
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--color-text-tertiary)",
          fontSize: 13,
          border: "1px dashed var(--color-border-tertiary)",
          borderRadius: 8,
        }}>
          No data — run a query to populate this chart
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          {renderChart()}
        </ResponsiveContainer>
      )}

      {/* Footer */}
      <div style={{ fontSize: 11, color: "var(--color-text-tertiary)", textAlign: "right" }}>
        Showing {Math.min(limit, data.length).toLocaleString()} of {data.length.toLocaleString()} rows
      </div>
    </div>
  );
}

// ─── Shared select style ──────────────────────────────────────────────────────

const selectStyle: React.CSSProperties = {
  fontSize: 12,
  padding: "3px 8px",
  borderRadius: 6,
  border: "1px solid var(--color-border-secondary)",
  background: "var(--color-background-secondary)",
  color: "var(--color-text-primary)",
  cursor: "pointer",
  outline: "none",
  maxWidth: 180,
};