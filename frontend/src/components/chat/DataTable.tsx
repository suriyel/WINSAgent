import { useState, useMemo, lazy, Suspense } from "react";
import type { TableData, ChartPending } from "../../types";

const AutoChart = lazy(() => import("../chart/AutoChart"));

interface Props {
  table: TableData;
  tableIndex?: number;
}

const ROWS_PER_PAGE = 10;
/** Minimum number of numeric columns required to show the chart toggle. */
const MIN_NUMERIC_COLS = 1;

/** Convert TableData (headers + string[][]) to flat rows for AutoChart. */
function tableToChartPending(table: TableData): ChartPending | null {
  if (table.rows.length === 0 || table.headers.length === 0) return null;

  // Detect which columns are numeric by sampling up to 20 rows
  const sampleSize = Math.min(table.rows.length, 20);
  const numericCols: Set<number> = new Set();
  for (let ci = 0; ci < table.headers.length; ci++) {
    let isNumeric = true;
    for (let ri = 0; ri < sampleSize; ri++) {
      const val = table.rows[ri]?.[ci]?.trim() ?? "";
      if (val === "") continue;
      if (isNaN(Number(val))) { isNumeric = false; break; }
    }
    if (isNumeric) numericCols.add(ci);
  }

  if (numericCols.size < MIN_NUMERIC_COLS) return null;

  const dimensions: string[] = [];
  const measures: string[] = [];
  const labels: Record<string, string> = {};

  for (let ci = 0; ci < table.headers.length; ci++) {
    const key = table.headers[ci];
    labels[key] = key;
    if (numericCols.has(ci)) {
      measures.push(key);
    } else {
      dimensions.push(key);
    }
  }

  const rows: Record<string, unknown>[] = table.rows.map((row) => {
    const obj: Record<string, unknown> = {};
    for (let ci = 0; ci < table.headers.length; ci++) {
      const key = table.headers[ci];
      const raw = row[ci] ?? "";
      obj[key] = numericCols.has(ci) ? Number(raw) || 0 : raw;
    }
    return obj;
  });

  return {
    execution_id: "",
    chart_type: "grouped_bar_chart",
    rows,
    meta: { dimensions, measures, labels },
  };
}

export default function DataTable({ table, tableIndex = 0 }: Props) {
  const [currentPage, setCurrentPage] = useState(0);
  const [showChart, setShowChart] = useState(false);

  const totalPages = Math.ceil(table.rows.length / ROWS_PER_PAGE);
  const startIdx = currentPage * ROWS_PER_PAGE;
  const endIdx = Math.min(startIdx + ROWS_PER_PAGE, table.rows.length);
  const visibleRows = table.rows.slice(startIdx, endIdx);

  const chartPending = useMemo(() => tableToChartPending(table), [table]);

  const handleExportCSV = () => {
    const lines = [
      table.headers.join(","),
      ...table.rows.map((row) => row.join(",")),
    ];
    const blob = new Blob([lines.join("\n")], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `table_${tableIndex}_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mt-2 space-y-2">
      {/* 元信息 + 操作按钮 */}
      <div className="flex items-center justify-between text-xs text-text-weak">
        <span>共 {table.total_rows} 条记录</span>
        <div className="flex items-center gap-1.5">
          {chartPending && (
            <button
              onClick={() => setShowChart((v) => !v)}
              className={`px-2 py-0.5 rounded border transition-colors ${
                showChart
                  ? "bg-primary/15 border-primary/40 text-primary"
                  : "border-gray-200 hover:bg-gray-50"
              }`}
              title={showChart ? "切换到表格" : "切换到图表"}
            >
              {showChart ? (
                <svg className="w-3.5 h-3.5 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 6h18M3 14h18M3 18h18" />
                </svg>
              ) : (
                <svg className="w-3.5 h-3.5 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              )}
            </button>
          )}
          <button
            onClick={handleExportCSV}
            className="px-2 py-0.5 rounded border border-gray-200 hover:bg-gray-50 transition-colors"
          >
            导出 CSV
          </button>
        </div>
      </div>

      {/* Chart view */}
      {showChart && chartPending ? (
        <Suspense fallback={<div className="h-40 flex items-center justify-center text-sm text-text-weak">加载图表...</div>}>
          <AutoChart chartPending={chartPending} />
        </Suspense>
      ) : (
        <>
          {/* 表格 */}
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs border-collapse">
              <thead>
                <tr className="bg-primary/10">
                  {table.headers.map((h, hi) => (
                    <th
                      key={hi}
                      className="px-2 py-1.5 text-left font-semibold text-text-primary border border-gray-200 whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row, ri) => (
                  <tr
                    key={startIdx + ri}
                    className={(startIdx + ri) % 2 === 0 ? "bg-white" : "bg-gray-50"}
                  >
                    {row.map((cell, ci) => (
                      <td
                        key={ci}
                        className="px-2 py-1 text-text-secondary border border-gray-200 whitespace-nowrap"
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 text-xs">
              <button
                onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
                disabled={currentPage === 0}
                className="px-2 py-1 border border-gray-200 rounded hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                上一页
              </button>
              <span className="text-text-weak">
                {currentPage + 1} / {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={currentPage === totalPages - 1}
                className="px-2 py-1 border border-gray-200 rounded hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                下一页
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
