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
  const [files, setFiles] = useState<File[]>([]);
  const [bundle, setBundle] = useState(
    Boolean(report.versions.at(-1)?.files?.length),
  );
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => reportsApi.upload(report.id, files, bundle),
    onSuccess: async (version) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["report", report.id] }),
        client.invalidateQueries({ queryKey: ["reports"] }),
      ]);
      onUploaded(version.id);
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
          choose(e.dataTransfer.files);
        }}
      >
        <Upload size={30} />
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
        onChange={(e) => choose(e.target.files ?? undefined)}
      />
      <div className="muted">
        <p>
          建立第 {report.versions.at(-1)!.number + 1}{" "}
          版時，請重新選擇此版本要包含的完整檔案組。
        </p>
        <p>
          單檔支援 demo 或 8 欄壽險承保；同次申報可提供承保、給付、填報對象
          CSV，每種類型最多一份。
        </p>
        <p>
          每檔上限 2 MB、最多 1,000 筆；後端依表頭辨識檔案類型並追蹤各檔來源。
        </p>
      </div>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={bundle}
          disabled={mutation.isPending}
          onChange={(event) => setBundle(event.target.checked)}
        />
        這些檔案組成同一次申報（完整取代上一版檔案組）
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
          disabled={!files.length || mutation.isPending}
          onClick={() => files.length && mutation.mutate()}
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
