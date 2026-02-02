import { useRef, useEffect, useState, useMemo, useCallback } from "react";
import { Chart } from "@antv/g2";
import { Advisor } from "@antv/ava";
import type { ChartPending, CellComparisonData } from "../../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  chartPending: ChartPending;
}

/** Flat row format used by G2 and AVA. */
interface FlatRow {
  cell_id: string;
  area: string;
  indicator: string;
  stage: string;
  value: number;
}

/** Merged advice entry combining backend + AVA recommendations. */
interface MergedAdvice {
  type: string;
  label: string;
  score: number;
  isBackendRecommended: boolean;
}

// ---------------------------------------------------------------------------
// Chart type configs — each type defines a label + G2 options builder
// ---------------------------------------------------------------------------

interface ChartTypeConfig {
  label: string;
  /** Build G2-compatible options from flat data. Return null to signal "not applicable". */
  buildOptions: (
    data: FlatRow[],
    indicators: string[],
    cells: CellComparisonData[],
  ) => Record<string, unknown> | null;
}

const CHART_TYPE_CONFIGS: Record<string, ChartTypeConfig> = {
  grouped_bar_chart: {
    label: "分组柱状图",
    buildOptions: (data, indicators) => ({
      type: "interval",
      data,
      encode: { x: "cell_id", y: "value", color: "stage" },
      transform: [{ type: "dodgeX" }],
      scale: {
        x: { type: "band", padding: 0.2 },
        color: { range: ["#60A5FA", "#34D399"] },
      },
      axis: {
        x: { title: "小区", labelAutoRotate: true },
        y: { title: indicators.length === 1 ? indicators[0] : "指标值" },
      },
      interaction: { tooltip: true },
      legend: { color: { position: "top" } },
    }),
  },

  line_chart: {
    label: "折线图",
    buildOptions: (data, indicators) => ({
      type: "line",
      data,
      encode: { x: "cell_id", y: "value", color: "stage" },
      scale: {
        color: { range: ["#60A5FA", "#34D399"] },
      },
      axis: {
        x: { title: "小区", labelAutoRotate: true },
        y: { title: indicators.length === 1 ? indicators[0] : "指标值" },
      },
      style: { lineWidth: 2 },
      interaction: { tooltip: true },
      legend: { color: { position: "top" } },
    }),
  },

  stacked_bar_chart: {
    label: "堆叠柱状图",
    buildOptions: (data, indicators) => ({
      type: "interval",
      data,
      encode: { x: "cell_id", y: "value", color: "stage" },
      transform: [{ type: "stackY" }],
      scale: {
        x: { type: "band", padding: 0.2 },
        color: { range: ["#60A5FA", "#34D399"] },
      },
      axis: {
        x: { title: "小区", labelAutoRotate: true },
        y: { title: indicators.length === 1 ? indicators[0] : "指标值" },
      },
      interaction: { tooltip: true },
      legend: { color: { position: "top" } },
    }),
  },

  scatter_plot: {
    label: "散点图",
    buildOptions: (_data, indicators, cells) => {
      // Scatter: x = before, y = after for first indicator
      const ind = indicators[0];
      if (!ind) return null;
      const scatterData = cells.map((c) => ({
        cell_id: c.cell_id,
        area: c.area,
        before: c.before[ind] ?? 0,
        after: c.after[ind] ?? 0,
        diff: c.diff[ind] ?? 0,
      }));
      return {
        type: "point",
        data: scatterData,
        encode: { x: "before", y: "after", size: "diff", color: "area" },
        scale: {
          color: { range: ["#A78BFA", "#60A5FA", "#34D399", "#FBBF24", "#F87171"] },
        },
        axis: {
          x: { title: `${ind} (优化前)` },
          y: { title: `${ind} (优化后)` },
        },
        style: { fillOpacity: 0.7 },
        interaction: { tooltip: true },
        legend: { color: { position: "top" } },
      };
    },
  },

  heatmap: {
    label: "热力图",
    buildOptions: (_data, indicators, cells) => {
      // Heatmap: x = cell_id, y = indicator, color = diff value
      const heatData: Record<string, unknown>[] = [];
      for (const cell of cells) {
        for (const ind of indicators) {
          heatData.push({
            cell_id: cell.cell_id,
            indicator: ind,
            diff: cell.diff[ind] ?? 0,
          });
        }
      }
      return {
        type: "cell",
        data: heatData,
        encode: { x: "cell_id", y: "indicator", color: "diff" },
        scale: {
          color: { palette: "RdYlGn", domain: [-10, 10] },
        },
        axis: {
          x: { title: "小区", labelAutoRotate: true },
          y: { title: "指标" },
        },
        style: { inset: 1 },
        interaction: { tooltip: true },
        legend: { color: { position: "top", title: "差值" } },
      };
    },
  },

  table: {
    label: "数据表格",
    // Table renders as HTML, not G2 — return null to skip chart rendering
    buildOptions: () => null,
  },
};

const SUPPORTED_CHART_TYPES = Object.keys(CHART_TYPE_CONFIGS);

// ---------------------------------------------------------------------------
// Data helpers
// ---------------------------------------------------------------------------

/** Flatten comparison cells into a row-per-indicator-per-stage format for G2/AVA. */
function flattenCells(
  cells: CellComparisonData[],
  indicators: string[],
): FlatRow[] {
  const rows: FlatRow[] = [];
  for (const cell of cells) {
    for (const ind of indicators) {
      rows.push({
        cell_id: cell.cell_id,
        area: cell.area,
        indicator: ind,
        stage: "优化前",
        value: cell.before[ind] ?? 0,
      });
      rows.push({
        cell_id: cell.cell_id,
        area: cell.area,
        indicator: ind,
        stage: "优化后",
        value: cell.after[ind] ?? 0,
      });
    }
  }
  return rows;
}

/** Merge backend chart_type with AVA advise results into a sorted list. */
function getMergedAdvices(
  avaAdvices: { type: string; score: number }[],
  backendChartType: string,
): MergedAdvice[] {
  // Collect unique types: backend first, then AVA in score order
  const seen = new Set<string>();
  const merged: MergedAdvice[] = [];

  const addType = (type: string, score: number, isBackend: boolean) => {
    if (seen.has(type) || !(type in CHART_TYPE_CONFIGS)) return;
    seen.add(type);
    merged.push({
      type,
      label: CHART_TYPE_CONFIGS[type].label,
      score,
      isBackendRecommended: isBackend,
    });
  };

  // Backend recommendation first
  addType(backendChartType, 100, true);

  // AVA recommendations
  for (const adv of avaAdvices) {
    addType(adv.type, adv.score, false);
  }

  // Add remaining supported types not yet included (with score 0)
  for (const type of SUPPORTED_CHART_TYPES) {
    addType(type, 0, false);
  }

  return merged;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ComparisonChart({ chartPending }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Chart | null>(null);

  const { data, chart_type: backendChartType } = chartPending;

  // ----- Filter state -----
  const [selectedAreas, setSelectedAreas] = useState<string[]>(data.filters.areas);
  const [selectedIndicators, setSelectedIndicators] = useState<string[]>(data.indicators);
  const [threshold, setThreshold] = useState(data.filters.threshold);
  const [collapsed, setCollapsed] = useState(false);
  const [renderChartType, setRenderChartType] = useState<string>(
    backendChartType in CHART_TYPE_CONFIGS ? backendChartType : "grouped_bar_chart",
  );

  // Reset filters when data changes
  useEffect(() => {
    setSelectedAreas(data.filters.areas);
    setSelectedIndicators(data.indicators);
    setThreshold(data.filters.threshold);
    setRenderChartType(
      backendChartType in CHART_TYPE_CONFIGS ? backendChartType : "grouped_bar_chart",
    );
  }, [data, backendChartType]);

  // ----- Filtered cells -----
  const filteredCells = useMemo(() => {
    return data.cells.filter((cell) => {
      const areaMatch = selectedAreas.length === 0 || selectedAreas.includes(cell.area);
      const thresholdMatch = selectedIndicators.some(
        (ind) => Math.abs(cell.diff[ind] ?? 0) >= threshold,
      );
      return areaMatch && thresholdMatch;
    });
  }, [data.cells, selectedAreas, selectedIndicators, threshold]);

  // ----- Flat data for chart -----
  const flatData = useMemo(
    () => flattenCells(filteredCells, selectedIndicators),
    [filteredCells, selectedIndicators],
  );

  // ----- AVA recommendation -----
  const avaAdvices = useMemo(() => {
    if (flatData.length === 0) return [];
    try {
      const advisor = new Advisor();
      const results = advisor.advise({
        data: flatData as unknown as Record<string, unknown>[],
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
  }, [flatData]);

  // ----- Merged advices (backend + AVA) -----
  const mergedAdvices = useMemo(
    () => getMergedAdvices(avaAdvices, backendChartType),
    [avaAdvices, backendChartType],
  );

  // ----- Build G2 options for current chart type -----
  const chartOptions = useMemo(() => {
    const config = CHART_TYPE_CONFIGS[renderChartType];
    if (!config) return null;
    return config.buildOptions(flatData, selectedIndicators, filteredCells);
  }, [renderChartType, flatData, selectedIndicators, filteredCells]);

  // ----- G2 Render -----
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

  // ----- Area toggle -----
  const toggleArea = useCallback((area: string) => {
    setSelectedAreas((prev) => {
      if (prev.includes(area)) {
        const next = prev.filter((a) => a !== area);
        return next.length === 0 ? data.filters.areas : next;
      }
      return [...prev, area];
    });
  }, [data.filters.areas]);

  // ----- Indicator toggle -----
  const toggleIndicator = useCallback((ind: string) => {
    setSelectedIndicators((prev) => {
      if (prev.includes(ind)) {
        if (prev.length <= 1) return prev;
        return prev.filter((i) => i !== ind);
      }
      return [...prev, ind];
    });
  }, []);

  // ----- Statistics -----
  const summaryStats = data.statistics.summary.avg_improvement;

  // ----- Is table mode -----
  const isTableMode = renderChartType === "table";

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
          <span className="text-sm font-semibold text-text-primary">仿真前后对比图表</span>
          <span className="text-xs text-text-weak">
            {filteredCells.length} 个小区 · {selectedIndicators.length} 项指标
          </span>
        </div>
        <svg
          className={`w-4 h-4 text-text-secondary transition-transform ${collapsed ? "rotate-0" : "rotate-180"}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      {!collapsed && (
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
                {advice.isBackendRecommended && (
                  <span className="ml-1 opacity-70">*</span>
                )}
              </button>
            ))}
          </div>

          {/* Filters toolbar */}
          <div className="flex flex-wrap gap-3 text-xs">
            {/* Area filter */}
            {data.filters.areas.length > 1 && (
              <div className="flex items-center gap-1.5">
                <span className="text-text-secondary font-medium">区域:</span>
                {data.filters.areas.map((area) => (
                  <button
                    key={area}
                    onClick={() => toggleArea(area)}
                    className={`px-2 py-0.5 rounded-full border transition-colors ${
                      selectedAreas.includes(area)
                        ? "bg-primary/15 border-primary/40 text-primary"
                        : "bg-gray-50 border-gray-200 text-text-weak"
                    }`}
                  >
                    {area}
                  </button>
                ))}
              </div>
            )}

            {/* Indicator filter */}
            <div className="flex items-center gap-1.5">
              <span className="text-text-secondary font-medium">指标:</span>
              {data.indicators.map((ind) => (
                <button
                  key={ind}
                  onClick={() => toggleIndicator(ind)}
                  className={`px-2 py-0.5 rounded-full border transition-colors ${
                    selectedIndicators.includes(ind)
                      ? "bg-secondary/15 border-secondary/40 text-secondary"
                      : "bg-gray-50 border-gray-200 text-text-weak"
                  }`}
                >
                  {ind}
                </button>
              ))}
            </div>

            {/* Threshold slider */}
            <div className="flex items-center gap-1.5">
              <span className="text-text-secondary font-medium">阈值:</span>
              <input
                type="range"
                min={0}
                max={10}
                step={0.5}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                className="w-20 h-1 accent-primary"
              />
              <span className="text-text-weak w-6 text-right">{threshold}</span>
            </div>
          </div>

          {/* Chart / Table / Empty */}
          {flatData.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-text-weak text-sm">
              无满足条件的数据
            </div>
          ) : isTableMode ? (
            <ComparisonTable cells={filteredCells} indicators={selectedIndicators} />
          ) : chartOptions ? (
            <div ref={containerRef} className="w-full" style={{ minHeight: 360 }} />
          ) : (
            <div className="flex items-center justify-center h-40 text-text-weak text-sm">
              该图表类型不适用于当前数据
            </div>
          )}

          {/* Statistics summary */}
          <div className="flex flex-wrap gap-3 pt-2 border-t border-gray-100">
            {Object.entries(summaryStats).map(([ind, value]) => (
              <div key={ind} className="flex items-center gap-1.5 text-xs">
                <span className="text-text-secondary">{ind}:</span>
                <span className={`font-semibold ${(value as number) > 0 ? "text-success" : (value as number) < 0 ? "text-error" : "text-text-weak"}`}>
                  {(value as number) > 0 ? "+" : ""}{(value as number).toFixed(2)}
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
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table sub-component (for "table" chart type)
// ---------------------------------------------------------------------------

function ComparisonTable({
  cells,
  indicators,
}: {
  cells: CellComparisonData[];
  indicators: string[];
}) {
  return (
    <div className="overflow-x-auto max-h-80 overflow-y-auto">
      <table className="min-w-full text-xs border-collapse">
        <thead className="sticky top-0">
          <tr className="bg-primary/10">
            <th className="px-2 py-1.5 text-left font-semibold text-text-primary border border-gray-200">小区</th>
            <th className="px-2 py-1.5 text-left font-semibold text-text-primary border border-gray-200">区域</th>
            {indicators.map((ind) => (
              <th key={`b-${ind}`} className="px-2 py-1.5 text-right font-semibold text-text-primary border border-gray-200 whitespace-nowrap">
                {ind}<br /><span className="font-normal text-text-weak">优化前</span>
              </th>
            ))}
            {indicators.map((ind) => (
              <th key={`a-${ind}`} className="px-2 py-1.5 text-right font-semibold text-text-primary border border-gray-200 whitespace-nowrap">
                {ind}<br /><span className="font-normal text-text-weak">优化后</span>
              </th>
            ))}
            {indicators.map((ind) => (
              <th key={`d-${ind}`} className="px-2 py-1.5 text-right font-semibold text-text-primary border border-gray-200 whitespace-nowrap">
                {ind}<br /><span className="font-normal text-text-weak">差值</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cells.map((cell, ri) => (
            <tr key={cell.cell_id} className={ri % 2 === 0 ? "bg-white" : "bg-gray-50"}>
              <td className="px-2 py-1 text-text-secondary border border-gray-200 whitespace-nowrap">{cell.cell_id}</td>
              <td className="px-2 py-1 text-text-secondary border border-gray-200">{cell.area}</td>
              {indicators.map((ind) => (
                <td key={`b-${ind}`} className="px-2 py-1 text-right text-text-secondary border border-gray-200">
                  {(cell.before[ind] ?? 0).toFixed(1)}
                </td>
              ))}
              {indicators.map((ind) => (
                <td key={`a-${ind}`} className="px-2 py-1 text-right text-text-secondary border border-gray-200">
                  {(cell.after[ind] ?? 0).toFixed(1)}
                </td>
              ))}
              {indicators.map((ind) => {
                const d = cell.diff[ind] ?? 0;
                return (
                  <td
                    key={`d-${ind}`}
                    className={`px-2 py-1 text-right font-medium border border-gray-200 ${
                      d > 0 ? "text-success" : d < 0 ? "text-error" : "text-text-weak"
                    }`}
                  >
                    {d > 0 ? "+" : ""}{d.toFixed(2)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
