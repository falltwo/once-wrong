import { useEffect, useRef } from "react";
import { MotionConfig, motion } from "framer-motion";
import { ArrowLeft, BookOpen, ChevronRight, ExternalLink, ShieldCheck } from "lucide-react";
import { reportsApi } from "../../api/reports";
import type { Citation } from "../../types";

function location(citation: Citation): string {
  return [citation.section.join(" › "), citation.page ? `第 ${citation.page} 頁` : ""]
    .filter(Boolean)
    .join(" · ");
}

/** 原文中標出 quote；quote 不是原文的子字串時（後端核對失敗）一律不標。 */
function Highlighted({ text, quote }: { text: string; quote?: string | null }) {
  const start = quote ? text.indexOf(quote) : -1;
  if (!quote || start < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, start)}
      <mark>{quote}</mark>
      {text.slice(start + quote.length)}
    </>
  );
}

export function ManualEvidenceList({
  citations,
  rejectedQuotes,
  onOpen,
}: {
  citations: Citation[];
  rejectedQuotes: number;
  onOpen: (citation: Citation) => void;
}) {
  return (
    <section className="suggestion-citations" aria-label="手冊依據">
      <strong>手冊依據</strong>
      <ul>
        {citations.map((citation) => (
          <li key={citation.id}>
            <button className="evidence-card" onClick={() => onOpen(citation)}>
              <BookOpen size={15} aria-hidden="true" />
              <span className="evidence-card-text">
                <span>{citation.source}</span>
                {location(citation) && <small>{location(citation)}</small>}
                {citation.excerpt && <q>{citation.quote ?? citation.excerpt}</q>}
                {citation.quote && (
                  <em>
                    <ShieldCheck size={12} aria-hidden="true" />
                    已逐字核對原文
                  </em>
                )}
              </span>
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      {rejectedQuotes > 0 && (
        <p className="evidence-rejected" role="status">
          AI 有 {rejectedQuotes} 句引用在手冊原文中找不到，已攔下不顯示。
        </p>
      )}
    </section>
  );
}

/** Cinnabar seal for an error that a later version fixed (and kept fixed). */
export function Seal({ fixedIn }: { fixedIn: number }) {
  return (
    <span className="seal" role="img" aria-label={`這個錯誤已在第 ${fixedIn} 版修正`}>
      <strong>已修正</strong>
      <small>第 {fixedIn} 版</small>
      <b>OW</b>
    </span>
  );
}

/** SVG filter that roughens the paper edge (deckled, hand-torn look). Rendered once per view. */
function DeckleFilter() {
  return (
    <svg width="0" height="0" aria-hidden="true" style={{ position: "absolute" }}>
      <filter id="ow-deckle" x="-5%" y="-5%" width="110%" height="110%">
        <feTurbulence type="fractalNoise" baseFrequency="0.045" numOctaves="3" seed="7" />
        <feDisplacementMap in="SourceGraphic" scale="7" xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </svg>
  );
}

export function ManualEvidenceView({
  citation,
  fixedIn,
  onBack,
}: {
  citation: Citation;
  /** Version that fixed this error, when a later version no longer has it. */
  fixedIn?: number;
  onBack: () => void;
}) {
  const backRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    // The page is still visibility:hidden until the slide starts, so focus one frame later.
    const frame = requestAnimationFrame(() => backRef.current?.focus());
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("keydown", onKey);
    };
  }, [onBack]);

  return (
    <div className="evidence-view">
      <button ref={backRef} className="evidence-back" onClick={onBack}>
        <ArrowLeft size={15} aria-hidden="true" />
        返回說明
      </button>
      <span className="eyebrow">手冊依據</span>
      <h3>{citation.source}</h3>
      {location(citation) && <p className="muted">{location(citation)}</p>}

      {citation.excerpt ? (
        <>
          <MotionConfig reducedMotion="user">
          {/* Heavy page opening on its spine: overshoots past rest, then settles (spring). */}
          <motion.div
            className="evidence-sheet"
            initial={{ rotateY: -78, opacity: 0 }}
            animate={{ rotateY: -5, opacity: 1 }}
            transition={{
              rotateY: { type: "spring", stiffness: 120, damping: 11, mass: 1.1 },
              opacity: { duration: 0.25 },
            }}
          >
            <DeckleFilter />
            <span className="evidence-binding" aria-hidden="true" />
            {citation.page ? (
              <span className="evidence-ribbon" aria-label={`第 ${citation.page} 頁`}>
                第 {citation.page} 頁
              </span>
            ) : null}
            <blockquote className="evidence-page">
              <Highlighted text={citation.excerpt} quote={citation.quote} />
            </blockquote>
            {fixedIn ? <Seal fixedIn={fixedIn} /> : null}
          </motion.div>
          </MotionConfig>
          <p className="evidence-note">
            {citation.quote
              ? "螢光處是 AI 說明依據的句子，系統已逐字核對它確實出現在這段原文。"
              : "AI 沒有指出依據哪一句，因此不做標記。"}
            以上是從手冊抽出的文字，排版與原始頁面不同。
          </p>
        </>
      ) : (
        <p className="neutral-notice">這段引用只有出處，系統沒有提供手冊原文。</p>
      )}

      {citation.pdfUrl && citation.page ? (
        <a
          className="evidence-pdf"
          href={reportsApi.apiUrl(citation.pdfUrl)}
          target="_blank"
          rel="noopener noreferrer"
        >
          <ExternalLink size={14} aria-hidden="true" />
          開啟原始手冊第 {citation.page} 頁
        </a>
      ) : (
        <p className="evidence-note">原始手冊未在此系統提供，請以團隊持有的版本核對。</p>
      )}
    </div>
  );
}
