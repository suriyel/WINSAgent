import { useRef, useEffect, useState, useMemo, useCallback } from "react";
import { Chart } from "@antv/g2";
import { Advisor } from "@antv/ava";
import type { ChartPending, ChartMeta } from "../../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  chartPending: ChartPending;
  /** Hide the collapsible header (used when embedded inside DataTable). */
  embedded?: boolean;
}

/** Merged advice entry combining backend + AVA recommendations. */
interface MergedAdvice {
  type: string;
  label: string;
  score: number;
  isBackend: boolean;
}

// ---------------------------------------------------------------------------
// Chart type configs — each type defines a label + G2 options builder
// ---------------------------------------------------------------------------

interface ChartTypeConfig {
  label: string;
  buildOptions: (
    data: Record<string, unknown>[],
    meta: ChartMeta,
  ) => Record<string, unknown> | null;
}

const COLOR_PALETTE = ["#60A5FA", "#34D399", "#A78BFA", "#FBBF24", "#F87171"];

const CHART_TYPE_CONFIGS: Record<string, ChartTypeConfig> = {
  grouped_bar_chart: {
    label: "分组柱状图",
    buildOptions: (data, meta) => {
      const dims = meta.dimensions ?? [];
      const measure = (meta.measures ?? ["value"])[0];
      const xField = dims[0] ?? "x";
      const colorField = dims.length > 1 ? dims[dims.length - 1] : undefined;
      return {
        type: "interval",
        data,
        encode: { x: xField, y: measure, ...(colorField ? { color: colorField } : {}) },
        transform: colorField ? [{ type: "dodgeX" }] : [],
        scale: {
          x: { type: "band", padding: 0.2 },
          color: { range: COLOR_PALETTE },
        },
        axis: {
          x: { title: meta.labels?.[xField] ?? xField, labelAutoRotate: true },
          y: { title: meta.labels?.[measure] ?? measure },
        },
        interaction: { tooltip: true },
        legend: colorField ? { color: { position: "top" } } : undefined,
      };
    },
  },

  line_chart: {
    label: "折线图",
    buildOptions: (data, meta) => {
      const dims = meta.dimensions ?? [];
      const measure = (meta.measures ?? ["value"])[0];
      const xField = dims[0] ?? "x";
      const colorField = dims.length > 1 ? dims[dims.length - 1] : undefined;
      return {
        type: "line",
        data,
        encode: { x: xField, y: measure, ...(colorField ? { color: colorField } : {}) },
        scale: { color: { range: COLOR_PALETTE } },
        axis: {
          x: { title: meta.labels?.[xField] ?? xField, labelAutoRotate: true },
          y: { title: meta.labels?.[measure] ?? measure },
        },
        style: { lineWidth: 2 },
        interaction: { tooltip: true },
        legend: colorField ? { color: { position: "top" } } : undefined,
      };
    },
  },

  stacked_bar_chart: {
    label: "堆叠柱状图",
    buildOptions: (data, meta) => {
      const dims = meta.dimensions ?? [];
      const measure = (meta.measures ?? ["value"])[0];
      const xField = dims[0] ?? "x";
      const colorField = dims.length > 1 ? dims[dims.length - 1] : undefined;
      return {
        type: "interval",
        data,
        encode: { x: xField, y: measure, ...(colorField ? { color: colorField } : {}) },
        transform: colorField ? [{ type: "stackY" }] : [],
        scale: {
          x: { type: "band", padding: 0.2 },
          color: { range: COLOR_PALETTE },
        },
        axis: {
          x: { title: meta.labels?.[xField] ?? xField, labelAutoRotate: true },
          y: { title: meta.labels?.[measure] ?? measure },
        },
        interaction: { tooltip: true },
        legend: colorField ? { color: { position: "top" } } : undefined,
      };
    },
  },

  scatter_plot: {
    label: "散点图",
    buildOptions: (data, meta) => {
      const dims = meta.dimensions ?? [];
      const measures = meta.measures ?? [];
      if (measures.length < 1) return null;
      const yField = measures[0];
      const xField = dims[0] ?? "x";
      const colorField = dims.length > 1 ? dims[1] : undefined;
      return {
        type: "point",
        data,
        encode: { x: xField, y: yField, ...(colorField ? { color: colorField } : {}) },
        scale: { color: { range: COLOR_PALETTE } },
        style: { fillOpacity: 0.7, r: 4 },
        interaction: { tooltip: true },
        legend: colorField ? { color: { position: "top" } } : undefined,
      };
    },
  },

  heatmap: {
    label: "热力图",
    buildOptions: (data, meta) => {
      const dims = meta.dimensions ?? [];
      const measure = (meta.measures ?? ["value"])[0];
      if (dims.length < 2) return null;
      return {
        type: "cell",
        data,
        encode: { x: dims[0], y: dims[1], color: measure },
        scale: { color: { palette: "RdYlGn" } },
        axis: {
          x: { title: meta.labels?.[dims[0]] ?? dims[0], labelAutoRotate: true },
          y: { title: meta.labels?.[dims[1]] ?? dims[1] },
        },
        style: { inset: 1 },
        interaction: { tooltip: true },
        legend: { color: { position: "top", title: meta.labels?.[measure] ?? measure } },
      };
    },
  },

  table: {
    label: "数据表格",
    buildOptions: () => null,
  },
};

const SUPPORTED_CHART_TYPES = Object.keys(CHART_TYPE_CONFIGS);

/** Max unique values for a dimension to appear as filter chips. */
const DIM_FILTER_MAX = 20;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AutoChart({ chartPending, embedded }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Chart | null>(null);

  const { rows, chart_type: backendChartType, title, meta: rawMeta } = chartPending;
  const meta: ChartMeta = rawMeta ?? {};
  const allMeasures = meta.measures ?? [];

  const [collapsed, setCollapsed] = useState(false);
  const [renderChartType, setRenderChartType] = useState(
    backendChartType in CHART_TYPE_CONFIGS ? backendChartType : "grouped_bar_chart",
  );

  // Selected measure (for multi-measure datasets)
  const [selectedMeasure, setSelectedMeasure] = useState<string>(allMeasures[0] ?? "value");

  // Dimension filters: dim key → selected values
  const [dimFilters, setDimFilters] = useState<Record<string, Set<string>>>({});

  // Extract filterable dimension values (2–DIM_FILTER_MAX unique values)
  const dimValues = useMemo(() => {
    const result: Record<string, string[]> = {};
    for (const dim of meta.dimensions ?? []) {
      const vals = new Set<string>();
      for (const row of rows) {
        const v = row[dim];
        if (v != null) vals.add(String(v));
      }
      if (vals.size >= 2 && vals.size <= DIM_FILTER_MAX) {
        result[dim] = Array.from(vals).sort();
      }
    }
    return result;
  }, [rows, meta.dimensions]);

  // Reset filters when data changes
  useEffect(() => {
    const initial: Record<string, Set<string>> = {};
    for (const [dim, vals] of Object.entries(dimValues)) {
      initial[dim] = new Set(vals);
    }
    setDimFilters(initial);
    setRenderChartType(
      backendChartType in CHART_TYPE_CONFIGS ? backendChartType : "grouped_bar_chart",
    );
    setSelectedMeasure(allMeasures[0] ?? "value");
  }, [dimValues, backendChartType, allMeasures]);

  // Effective meta with only the selected measure (for chart builders)
  const effectiveMeta = useMemo<ChartMeta>(() => ({
    ...meta,
    measures: [selectedMeasure],
  }), [meta, selectedMeasure]);

  // Filtered rows
  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      for (const [dim, selected] of Object.entries(dimFilters)) {
        const val = row[dim];
        if (val != null && !selected.has(String(val))) return false;
      }
      return true;
    });
  }, [rows, dimFilters]);

  // AVA recommendation
  const avaAdvices = useMemo(() => {
    if (filteredRows.length === 0) return [];
    try {
      const advisor = new Advisor();
      const results = advisor.advise({
        data: filteredRows as Record<string, unknown>[],
        options: {
          purpose: "Comparison",
          refine: true,
          theme: { primaryColor: "#A78BFA" },
        },
      });
      return results.map((r: { type: string; score: number }) => ({
        type: r.type,
        score: r.score,
      }));
    } catch {
      return [];
    }
  }, [filteredRows]);

  // Merged advices: backend first, then AVA, then remaining types.
  // Only include types that are applicable to the current data.
  const mergedAdvices = useMemo(() => {
    const seen = new Set<string>();
    const list: MergedAdvice[] = [];
    const add = (type: string, score: number, isBackend: boolean) => {
      if (seen.has(type) || !(type in CHART_TYPE_CONFIGS)) return;
      const config = CHART_TYPE_CONFIGS[type];
      // "table" always applicable; others must produce non-null options
      if (type !== "table" && config.buildOptions(filteredRows, effectiveMeta) === null) return;
      seen.add(type);
      list.push({ type, label: config.label, score, isBackend });
    };
    add(backendChartType, 100, true);
    for (const a of avaAdvices) add(a.type, a.score, false);
    for (const t of SUPPORTED_CHART_TYPES) add(t, 0, false);
    return list;
  }, [avaAdvices, backendChartType, filteredRows, effectiveMeta]);

  // Build G2 options using effectiveMeta (single selected measure)
  const chartOptions = useMemo(() => {
    const config = CHART_TYPE_CONFIGS[renderChartType];
    if (!config) return null;
    return config.buildOptions(filteredRows, effectiveMeta);
  }, [renderChartType, filteredRows, effectiveMeta]);

  // G2 render
  useEffect(() => {
    if (!containerRef.current || !chartOptions || collapsed) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const chart = new Chart({
      container: containerRef.current,
      autoFit: true,
      height: 360,
    });

    chart.options({ ...chartOptions, autoFit: true });
    chart.render();
    chartRef.current = chart;

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [chartOptions, collapsed]);

  // Toggle a dimension filter value
  const toggleDimValue = useCallback((dim: string, val: string) => {
    setDimFilters((prev) => {
      const current = prev[dim] ?? new Set();
      const next = new Set(current);
      if (next.has(val)) {
        next.delete(val);
        if (next.size === 0) return { ...prev, [dim]: new Set(dimValues[dim] ?? []) };
      } else {
        next.add(val);
      }
      return { ...prev, [dim]: next };
    });
  }, [dimValues]);

  const isTableMode = renderChartType === "table";
  const summary = meta.summary as Record<string, Record<string, number>> | undefined;
  const hasFilters = Object.keys(dimValues).length > 0;
  const hasMultipleMeasures = allMeasures.length > 1;

  const chartBody = (
    <div className="px-4 py-3 space-y-3">
      {/* Chart type switcher */}
      <div className="flex flex-wrap gap-1.5 text-xs">
        {mergedAdvices.map((advice) => (
          <button
            key={advice.type}
            onClick={() => setRenderChartType(advice.type)}
            className={`px-2.5 py-1 rounded-md border transition-colors ${
              renderChartType === advice.type
                ? "bg-primary text-white border-primary"
                : "bg-gray-50 border-gray-200 text-text-secondary hover:border-primary/40"
            }`}
          >
            {advice.label}
            {advice.isBackend && <span className="ml-1 opacity-70">*</span>}
          </button>
        ))}
      </div>

      {/* Measure selector (multi-measure datasets) */}
      {hasMultipleMeasures && (
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-text-secondary font-medium">Y轴指标:</span>
          {allMeasures.map((m) => (
            <button
              key={m}
              onClick={() => setSelectedMeasure(m)}
              className={`px-2 py-0.5 rounded-full border transition-colors ${
                selectedMeasure === m
                  ? "bg-secondary/15 border-secondary/40 text-secondary"
                  : "bg-gray-50 border-gray-200 text-text-weak"
              }`}
            >
              {meta.labels?.[m] ?? m}
            </button>
          ))}
        </div>
      )}

      {/* Dimension filters */}
      {hasFilters && (
        <div className="flex flex-wrap gap-3 text-xs">
          {Object.entries(dimValues).map(([dim, vals]) => (
            <div key={dim} className="flex items-center gap-1.5">
              <span className="text-text-secondary font-medium">
                {meta.labels?.[dim] ?? dim}:
              </span>
              {vals.map((val) => (
                <button
                  key={val}
                  onClick={() => toggleDimValue(dim, val)}
                  className={`px-2 py-0.5 rounded-full border transition-colors ${
                    (dimFilters[dim] ?? new Set()).has(val)
                      ? "bg-primary/15 border-primary/40 text-primary"
                      : "bg-gray-50 border-gray-200 text-text-weak"
                  }`}
                >
                  {val}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Chart / Table / Empty */}
      {filteredRows.length === 0 ? (
        <div className="flex items-center justify-center h-40 text-text-weak text-sm">
          无满足条件的数据
        </div>
      ) : isTableMode ? (
        <GenericTable rows={filteredRows} meta={meta} />
      ) : chartOptions ? (
        <div ref={containerRef} className="w-full" style={{ minHeight: 360 }} />
      ) : (
        <div className="flex items-center justify-center h-40 text-text-weak text-sm">
          该图表类型不适用于当前数据
        </div>
      )}

      {/* Summary stats (if provided in meta) */}
      {summary?.avg_improvement && (
        <div className="flex flex-wrap gap-3 pt-2 border-t border-gray-100">
          {Object.entries(summary.avg_improvement).map(([ind, value]) => (
            <div key={ind} className="flex items-center gap-1.5 text-xs">
              <span className="text-text-secondary">{ind}:</span>
              <span className={`font-semibold ${value > 0 ? "text-success" : value < 0 ? "text-error" : "text-text-weak"}`}>
                {value > 0 ? "+" : ""}{value.toFixed(2)}
              </span>
              <span className="text-text-weak">均值提升</span>
            </div>
          ))}
          {avaAdvices.length > 0 && (
            <div className="ml-auto text-xs text-text-weak">
              AVA 推荐: {CHART_TYPE_CONFIGS[avaAdvices[0].type]?.label ?? avaAdvices[0].type}
            </div>
          )}
        </div>
      )}
    </div>
  );

  // Embedded mode: no collapsible header
  if (embedded) {
    return <div className="rounded-lg border border-primary/20 bg-white overflow-hidden">{chartBody}</div>;
  }

  return (
    <div className="rounded-lg border border-primary/30 bg-white overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-primary/10 to-secondary/10 cursor-pointer select-none"
        onClick={() => setCollapsed((c) => !c)}
      >
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <span className="text-sm font-semibold text-text-primary">{title ?? "数据图表"}</span>
          <span className="text-xs text-text-weak">{filteredRows.length} 条记录</span>
        </div>
        <svg
          className={`w-4 h-4 text-text-secondary transition-transform ${collapsed ? "rotate-0" : "rotate-180"}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      {!collapsed && chartBody}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Generic table sub-component (for "table" chart type)
// ---------------------------------------------------------------------------

function GenericTable({
  rows,
  meta,
}: {
  rows: Record<string, unknown>[];
  meta: ChartMeta;
}) {
  if (rows.length === 0) return null;
  const keys = Object.keys(rows[0]);

  return (
    <div className="overflow-x-auto max-h-80 overflow-y-auto">
      <table className="min-w-full text-xs border-collapse">
        <thead className="sticky top-0">
          <tr className="bg-primary/10">
            {keys.map((k) => (
              <th key={k} className="px-2 py-1.5 text-left font-semibold text-text-primary border border-gray-200 whitespace-nowrap">
                {meta.labels?.[k] ?? k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className={ri % 2 === 0 ? "bg-white" : "bg-gray-50"}>
              {keys.map((k) => (
                <td key={k} className="px-2 py-1 text-text-secondary border border-gray-200 whitespace-nowrap">
                  {typeof row[k] === "number" ? (row[k] as number).toFixed(2) : String(row[k] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
