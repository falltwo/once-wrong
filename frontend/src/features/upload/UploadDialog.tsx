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
      <p className="muted">
        必要欄位：<code>id, product, previous, opening</code>
        <br />
        使用固定的 id，讓系統辨識跨版本的同一筆資料。
      </p>
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
