import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Upload } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { reportsApi } from "../../api/reports";
import { Dialog } from "../../components/Dialog";

export function CreateReportDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [period, setPeriod] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [bundle, setBundle] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const client = useQueryClient();
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: () => reportsApi.create(name.trim(), period, files, bundle),
    onSuccess: async (report) => {
      await client.invalidateQueries({ queryKey: ["reports"] });
      onClose();
      navigate(`/reports/${report.id}`);
    },
  });
  const choose = (selected: FileList | File[] | undefined) => {
    if (!mutation.isPending) {
      const selectedFiles = selected ? Array.from(selected) : [];
      setFiles(selectedFiles);
      if (selectedFiles.length > 1) setBundle(true);
      mutation.reset();
    }
  };
  const fileNames = files.map((selected) => selected.name).join("、");

  return (
    <Dialog
      title="新增報表・上傳第一版"
      onClose={onClose}
      busy={mutation.isPending}
    >
      <p className="muted">
        輸入報表名稱與月份，再上傳 CSV。後端會依表頭辨識資料格式，並建立第 1
        版。
      </p>
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
          choose(event.dataTransfer.files);
        }}
      >
        <Upload size={28} />
        <strong>{fileNames || "點擊選擇，或拖曳 CSV 到這裡"}</strong>
        <span>
          {files.length
            ? `${files.length} 個檔案`
            : "CSV UTF-8 · 每檔最大 2 MB · 最多 1,000 筆"}
        </span>
      </button>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        multiple
        hidden
        disabled={mutation.isPending}
        onChange={(event) => choose(event.target.files ?? undefined)}
      />
      <div className="muted">
        <p>支援單檔 demo／壽險承保，也可一次選同次申報的多個 CSV：</p>
        <p>
          <code>id, product, previous, opening</code>
        </p>
        <p>
          <code>
            公司代號, 保單編號, 保單編號序號, 異動序號, 加保別, 加保日期,
            退保別, 退保日期
          </code>
        </p>
        <p>
          多檔申報使用承保、給付、填報對象
          CSV；每種檔案最多一份。壽險欄位保留文字與前置 0。
        </p>
      </div>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={bundle}
          disabled={mutation.isPending}
          onChange={(event) => setBundle(event.target.checked)}
        />
        這些檔案組成同一次申報（使用多檔版本）
      </label>
      <div className="sample-links">
        <a href="/sample-errors.csv" download>
          含錯誤範例
        </a>
        <a href="/sample-fixed.csv" download>
          已修正範例
        </a>
      </div>
      {mutation.isError && (
        <p role="alert" className="error-message">
          {mutation.error.message}
        </p>
      )}
      <div className="dialog-actions">
        <button
          className="secondary"
          disabled={mutation.isPending}
          onClick={onClose}
        >
          取消
        </button>
        <button
          className="primary"
          disabled={
            !name.trim() || !period || !files.length || mutation.isPending
          }
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? (
            <>
              <LoaderCircle size={16} className="spin" />
              正在建立並檢核…
            </>
          ) : (
            "建立報表並檢核"
          )}
        </button>
      </div>
    </Dialog>
  );
}
