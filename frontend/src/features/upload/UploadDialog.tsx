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
  const isFiling = report.versions.at(-1)?.schemaProfileId === "life_filing_v1";
  const [bundle, setBundle] = useState(isFiling);
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: (selected: File[]) =>
      reportsApi.upload(report.id, selected, bundle),
    onSuccess: async (version) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["report", report.id] }),
        client.invalidateQueries({ queryKey: ["reports"] }),
      ]);
      onUploaded(version.id);
    },
  });
  const choose = (selected: File[]) => {
    if (!mutation.isPending) {
      setFiles(selected);
      if (selected.length > 1) setBundle(true);
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
          choose(Array.from(e.dataTransfer.files));
        }}
      >
        <Upload size={30} />
        <strong>
          {files.length
            ? files.map((file) => file.name).join("、")
            : "點擊選擇，或拖曳 CSV 到這裡"}
        </strong>
        <span>可選多份 CSV · UTF-8 · 每檔最大 2 MiB、1,000 筆</span>
      </button>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        multiple
        hidden
        disabled={mutation.isPending}
        onChange={(e) => choose(Array.from(e.target.files ?? []))}
      />
      <label className="filing-choice">
        <input
          type="checkbox"
          checked={bundle}
          disabled={isFiling || files.length > 1 || mutation.isPending}
          onChange={(event) => setBundle(event.target.checked)}
        />
        以同次申報的多檔版本檢核
      </label>
      <p className="muted">
        {bundle
          ? "每次提供完整的承保、給付與填報對象檔組；檔種由欄位辨識。缺少必要檔案時不能確認。"
          : "支援四欄示範 CSV 或八欄壽險承保 CSV。"}
        <br />
        上傳後建立新版本，原始資料與先前結果會保留。
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
          disabled={!files.length || mutation.isPending}
          onClick={() => files.length && mutation.mutate(files)}
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
