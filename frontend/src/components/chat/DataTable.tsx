import { useState, useMemo, lazy, Suspense } from "react";
import type { TableData, ChartPending } from "../../types";

const AutoChart = lazy(() => import("../chart/AutoChart"));

interface Props {
  table: TableData;
  tableIndex?: number;
}

const ROWS_PER_PAGE = 10;

/**
 * Column names that should be excluded from chartable measures
 * (coordinates, IDs that look numeric, etc.).
 */
const EXCLUDED_MEASURE_PATTERN =
  /^(longitude|latitude|lon|lat|经度|纬度|lng|x坐标|y坐标)$/i;

/** Convert TableData (headers + string[][]) to flat rows for AutoChart. */
function tableToChartPending(table: TableData): ChartPending | null {
  if (table.rows.length === 0 || table.headers.length === 0) return null;

  // Detect which columns are numeric by sampling up to 20 rows
  const sampleSize = Math.min(table.rows.length, 20);
  const numericCols = new Set<number>();
  for (let ci = 0; ci < table.headers.length; ci++) {
    let allNumeric = true;
    let hasValue = false;
    for (let ri = 0; ri < sampleSize; ri++) {
      const val = table.rows[ri]?.[ci]?.trim() ?? "";
      if (val === "") continue;
      hasValue = true;
      if (isNaN(Number(val))) { allNumeric = false; break; }
    }
    if (allNumeric && hasValue) numericCols.add(ci);
  }

  const dimensions: string[] = [];
  const measures: string[] = [];
  const labels: Record<string, string> = {};

  for (let ci = 0; ci < table.headers.length; ci++) {
    const key = table.headers[ci];
    labels[key] = key;

    if (numericCols.has(ci)) {
      // Exclude coordinate-like columns from measures
      if (EXCLUDED_MEASURE_PATTERN.test(key)) {
        // Don't add to dimensions either — too many unique values
        continue;
      }
      measures.push(key);
    } else {
      dimensions.push(key);
    }
  }

  // Need at least 1 dimension + 1 measure to be chartable
  if (measures.length < 1 || dimensions.length < 1) return null;

  const rows: Record<string, unknown>[] = table.rows.map((row) => {
    const obj: Record<string, unknown> = {};
    for (let ci = 0; ci < table.headers.length; ci++) {
      const key = table.headers[ci];
      // Skip excluded columns
      if (numericCols.has(ci) && EXCLUDED_MEASURE_PATTERN.test(key)) continue;
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
  const [viewMode, setViewMode] = useState<"table" | "chart">("table");

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
      {/* Tab bar + actions */}
      <div className="flex items-center text-xs">
        {/* View mode tabs */}
        <div className="flex items-center border-b border-gray-100">
          <button
            onClick={() => setViewMode("table")}
            className={`px-3 py-1.5 font-medium border-b-2 transition-colors ${
              viewMode === "table"
                ? "border-primary text-primary"
                : "border-transparent text-text-weak hover:text-text-secondary"
            }`}
          >
            <svg className="w-3.5 h-3.5 inline mr-1 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 6h18M3 14h18M3 18h18" />
            </svg>
            表格
          </button>
          {chartPending && (
            <button
              onClick={() => setViewMode("chart")}
              className={`px-3 py-1.5 font-medium border-b-2 transition-colors ${
                viewMode === "chart"
                  ? "border-primary text-primary"
                  : "border-transparent text-text-weak hover:text-text-secondary"
              }`}
            >
              <svg className="w-3.5 h-3.5 inline mr-1 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              图表
            </button>
          )}
        </div>

        <div className="flex-1" />

        {/* Meta + export */}
        <span className="text-text-weak mr-2">共 {table.total_rows} 条</span>
        <button
          onClick={handleExportCSV}
          className="px-2 py-0.5 rounded border border-gray-200 hover:bg-gray-50 transition-colors text-text-weak"
        >
          导出 CSV
        </button>
      </div>

      {/* Chart view */}
      {viewMode === "chart" && chartPending ? (
        <Suspense fallback={<div className="h-40 flex items-center justify-center text-sm text-text-weak">加载图表...</div>}>
          <AutoChart chartPending={chartPending} embedded />
        </Suspense>
      ) : (
        <>
          {/* Table view */}
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

          {/* Pagination */}
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
