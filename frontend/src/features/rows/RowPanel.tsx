import { CircleCheck, FileSpreadsheet, X } from "lucide-react";
import type { DataRow } from "../../types";
import { money } from "../../utils/format";
import { formatCell, lifeFieldLabels, rowLabel, rowValues } from "../../utils/reportData";

const demoLabels: Record<string, string> = {
  product: "險種",
  previous: "上月期末",
  opening: "本月期初",
};

/** 沒有錯誤的資料列：顯示整列內容，讓使用者也能點選、核對通過的資料。 */
export function RowPanel({
  row,
  columns,
  onClose,
}: {
  row: DataRow;
  columns: string[];
  onClose: () => void;
}) {
  const values = rowValues(row);
  return (
    <aside className="detail-panel">
      <div className="panel-title">
        <span>
          <FileSpreadsheet size={17} />
          資料列詳情
        </span>
        <button className="icon-button" aria-label="關閉資料列詳情" onClick={onClose}>
          <X size={17} />
        </button>
      </div>
      <div className="panel-body">
        <div className="issue-tags">
          <span className="status good">
            <CircleCheck size={13} />
            通過
          </span>
        </div>
        <h2>{rowLabel(row)}</h2>
        <p className="muted">這一列通過本版全部已執行的檢核規則。</p>
        <dl className="row-values">
          {columns.map((column) => {
            const value = values[column] ?? null;
            return (
              <div key={column}>
                <dt>{lifeFieldLabels[column] ?? demoLabels[column] ?? column}</dt>
                <dd>
                  {typeof value === "number" && (column === "previous" || column === "opening")
                    ? money(value)
                    : formatCell(value)}
                </dd>
              </div>
            );
          })}
        </dl>
      </div>
    </aside>
  );
}
