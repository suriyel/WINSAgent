import { useState } from "react";
import type { TableData } from "../../types";

interface Props {
  table: TableData;
  tableIndex?: number;
}

const ROWS_PER_PAGE = 10;

export default function DataTable({ table, tableIndex = 0 }: Props) {
  const [currentPage, setCurrentPage] = useState(0);

  const totalPages = Math.ceil(table.rows.length / ROWS_PER_PAGE);
  const startIdx = currentPage * ROWS_PER_PAGE;
  const endIdx = Math.min(startIdx + ROWS_PER_PAGE, table.rows.length);
  const visibleRows = table.rows.slice(startIdx, endIdx);

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
      {/* 元信息 + 导出 */}
      <div className="flex items-center justify-between text-xs text-text-weak">
        <span>共 {table.total_rows} 条记录</span>
        <button
          onClick={handleExportCSV}
          className="px-2 py-0.5 rounded border border-gray-200 hover:bg-gray-50 transition-colors"
        >
          导出 CSV
        </button>
      </div>

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
    </div>
  );
}
