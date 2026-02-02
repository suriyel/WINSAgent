import { useRef, useEffect, useState, useMemo, useCallback } from "react";
import { Chart } from "@antv/g2";
import { Advisor } from "@antv/ava";
import type { ChartPending } from "../../types";

interface Props {
  chartPending: ChartPending;
}

/** Flatten comparison cells into a row-per-indicator-per-stage format for G2/AVA. */
function flattenCells(
  cells: ChartPending["data"]["cells"],
  indicators: string[],
) {
  const rows: Record<string, unknown>[] = [];
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

export default function ComparisonChart({ chartPending }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Chart | null>(null);

  const { data } = chartPending;

  // ----- Filter state -----
  const [selectedAreas, setSelectedAreas] = useState<string[]>(data.filters.areas);
  const [selectedIndicators, setSelectedIndicators] = useState<string[]>(data.indicators);
  const [threshold, setThreshold] = useState(data.filters.threshold);
  const [collapsed, setCollapsed] = useState(false);

  // Reset filters when data changes
  useEffect(() => {
    setSelectedAreas(data.filters.areas);
    setSelectedIndicators(data.indicators);
    setThreshold(data.filters.threshold);
  }, [data]);

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
  const adviceList = useMemo(() => {
    if (flatData.length === 0) return [];
    try {
      const advisor = new Advisor();
      return advisor.advise({
        data: flatData as Record<string, unknown>[],
        options: {
          purpose: "Comparison",
          refine: true,
          theme: { primaryColor: "#A78BFA" },
        },
      });
    } catch {
      return [];
    }
  }, [flatData]);

  // AVA recommended chart type label
  const recommendedType = adviceList.length > 0 ? adviceList[0].type : "grouped_bar_chart";

  // ----- G2 Render -----
  useEffect(() => {
    if (!containerRef.current || flatData.length === 0 || collapsed) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const chart = new Chart({
      container: containerRef.current,
      autoFit: true,
      height: 360,
    });

    chart.options({
      type: "interval",
      data: flatData,
      encode: {
        x: "cell_id",
        y: "value",
        color: "stage",
      },
      transform: [{ type: "dodgeX" }],
      scale: {
        x: { type: "band", padding: 0.2 },
        color: { range: ["#60A5FA", "#34D399"] },
      },
      axis: {
        x: { title: "小区", labelAutoRotate: true },
        y: { title: selectedIndicators.length === 1 ? selectedIndicators[0] : "指标值" },
      },
      interaction: { tooltip: true },
      legend: { color: { position: "top" } },
    });

    chart.render();
    chartRef.current = chart;

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [flatData, collapsed, selectedIndicators]);

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
        if (prev.length <= 1) return prev; // keep at least one
        return prev.filter((i) => i !== ind);
      }
      return [...prev, ind];
    });
  }, []);

  // ----- Statistics -----
  const summaryStats = data.statistics.summary.avg_improvement;

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
          {/* Toolbar */}
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

          {/* Chart container */}
          {flatData.length > 0 ? (
            <div ref={containerRef} className="w-full" style={{ minHeight: 360 }} />
          ) : (
            <div className="flex items-center justify-center h-40 text-text-weak text-sm">
              无满足条件的数据
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
            {adviceList.length > 0 && (
              <div className="ml-auto text-xs text-text-weak">
                AVA 推荐: {recommendedType}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
