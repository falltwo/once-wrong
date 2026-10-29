import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Upload } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { reportsApi } from "../../api/reports";
import { Dialog } from "../../components/Dialog";

export function CreateReportDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [period, setPeriod] = useState("");
  const [file, setFile] = useState<File>();
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const client = useQueryClient();
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: () => reportsApi.create(name.trim(), period, file!),
    onSuccess: async (report) => {
      await client.invalidateQueries({ queryKey: ["reports"] });
      onClose();
      navigate(`/reports/${report.id}`);
    },
  });
  const choose = (selected?: File) => {
    if (!mutation.isPending) {
      setFile(selected);
      mutation.reset();
    }
  };

  return (
    <Dialog title="新增報表・上傳第一版" onClose={onClose} busy={mutation.isPending}>
      <p className="muted">輸入報表名稱與月份，再上傳 CSV。後端會依表頭辨識資料格式，並建立第 1 版。</p>
      <div className="new-report-fields">
        <label>
          報表名稱
          <input
            value={name}
            maxLength={120}
            placeholder="例如：準備金月報"
            disabled={mutation.isPending}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          報表期間
          <input
            type="month"
            value={period}
            disabled={mutation.isPending}
            onChange={(event) => setPeriod(event.target.value)}
          />
        </label>
      </div>
      <button
        type="button"
        className={`dropzone ${dragging ? "dragging" : ""}`}
        disabled={mutation.isPending}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          choose(event.dataTransfer.files[0]);
        }}
      >
        <Upload size={28} />
        <strong>{file?.name ?? "點擊選擇，或拖曳 CSV 到這裡"}</strong>
        <span>CSV UTF-8 · 最大 2 MB · 最多 1,000 筆</span>
      </button>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        hidden
        disabled={mutation.isPending}
        onChange={(event) => choose(event.target.files?.[0])}
      />
      <div className="muted">
        <p>支援兩種 CSV 表頭：</p>
        <p><code>id, product, previous, opening</code></p>
        <p><code>公司代號, 保單編號, 保單編號序號, 異動序號, 加保別, 加保日期, 退保別, 退保日期</code></p>
        <p>壽險欄位以文字保留，代號、序號與日期的前置 0 不會轉成數字。</p>
      </div>
      <div className="sample-links">
        <a href="/sample-errors.csv" download>含錯誤範例</a>
        <a href="/sample-fixed.csv" download>已修正範例</a>
      </div>
      {mutation.isError && (
        <p role="alert" className="error-message">{mutation.error.message}</p>
      )}
      <div className="dialog-actions">
        <button className="secondary" disabled={mutation.isPending} onClick={onClose}>
          取消
        </button>
        <button
          className="primary"
          disabled={!name.trim() || !period || !file || mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? (
            <><LoaderCircle size={16} className="spin" />正在建立並檢核…</>
          ) : "建立報表並檢核"}
        </button>
      </div>
    </Dialog>
  );
}
