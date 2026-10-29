import { AlertCircle, LoaderCircle } from "lucide-react";

export function Loading() {
  return (
    <div className="empty-state">
      <LoaderCircle className="spin" size={26} />
      <p>正在載入報表…</p>
    </div>
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: Error;
  retry: () => void;
}) {
  return (
    <div className="empty-state">
      <AlertCircle />
      <h2>暫時無法載入</h2>
      <p>{error.message}</p>
      <button onClick={retry}>重試</button>
    </div>
  );
}
