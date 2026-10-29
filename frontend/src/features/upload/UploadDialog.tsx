import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Upload } from "lucide-react";
import { reportsApi } from "../../api/reports";
import type { Report } from "../../types";
import { Dialog } from "../../components/Dialog";

export function UploadDialog({
  report,
  onClose,
  onUploaded,
}: {
  report: Report;
  onClose: () => void;
  onUploaded: (id: string) => void;
}) {
  const [file, setFile] = useState<File>();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: (selected: File) => reportsApi.upload(report.id, selected),
    onSuccess: async (version) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["report", report.id] }),
        client.invalidateQueries({ queryKey: ["reports"] }),
      ]);
      onUploaded(version.id);
    },
  });
  const choose = (selected?: File) => {
    if (!mutation.isPending) {
      setFile(selected);
      mutation.reset();
    }
  };
  return (
    <Dialog title="上傳修正版" onClose={onClose} busy={mutation.isPending}>
      <p className="muted">
        建立第 {report.versions.at(-1)!.number + 1} 版，保留先前的檢核紀錄。
      </p>
      <button
        className={`dropzone ${dragging ? "dragging" : ""}`}
        disabled={mutation.isPending}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          choose(e.dataTransfer.files[0]);
        }}
      >
        <Upload size={30} />
        <strong>{file?.name ?? "點擊選擇，或拖曳 CSV 到這裡"}</strong>
        <span>CSV UTF-8 · 最大 2 MB · 最多 1,000 筆</span>
      </button>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        hidden
        disabled={mutation.isPending}
        onChange={(e) => choose(e.target.files?.[0])}
      />
      <div className="muted">
        <p>請上傳與此報表相同格式的 CSV，後端會依表頭辨識 profile。</p>
        <p><code>demo_csv_v1</code>：<code>id, product, previous, opening</code></p>
        <p><code>life_underwriting_v1</code>：公司代號、保單編號、保單編號序號、異動序號、加保別、加保日期、退保別、退保日期（欄位順序可不同）</p>
        <p>CSV 上限 2 MB、最多 1,000 筆；壽險版本的重複錯誤目前依資料列位置比較。</p>
      </div>
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
          disabled={!file || mutation.isPending}
          onClick={() => file && mutation.mutate(file)}
        >
          {mutation.isPending ? (
            <>
              <LoaderCircle size={16} className="spin" />
              正在檢核…
            </>
          ) : (
            "上傳並檢核"
          )}
        </button>
      </div>
    </Dialog>
  );
}
