import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

type PageTurn = { key: number; from: number; to: number; backwards: boolean };
const reducedMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Locally synthesized stereo paper rustle, started only by an explicit version click. */
export function useArchivePageTurn() {
  const [turn, setTurn] = useState<PageTurn | null>(null);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const audio = useRef<AudioContext | null>(null);
  const source = useRef<AudioBufferSourceNode | null>(null);
  const enabled = useRef(true);
  const serial = useRef(0);

  useEffect(() => {
    if (!turn) return;
    const timer = window.setTimeout(() => setTurn(null), 1100);
    return () => window.clearTimeout(timer);
  }, [turn]);
  useEffect(
    () => () => {
      enabled.current = false;
      source.current?.stop();
      if (audio.current) void audio.current.close().catch(() => {});
      audio.current = null;
    },
    [],
  );

  const playPaper = async (backwards: boolean) => {
    try {
      const context = audio.current ?? new AudioContext();
      audio.current = context;
      if (context.state === "suspended") await context.resume();
      if (!enabled.current || reducedMotion() || context.state === "closed")
        return;
      source.current?.stop();
      const duration = 0.82;
      const buffer = context.createBuffer(
        1,
        Math.ceil(context.sampleRate * duration),
        context.sampleRate,
      );
      const samples = buffer.getChannelData(0);
      let previous = 0;
      for (let i = 0; i < samples.length; i += 1) {
        previous = (previous + (Math.random() * 2 - 1) * 0.16) / 1.16;
        samples[i] = previous * 3;
      }
      const paper = context.createBufferSource();
      const filter = context.createBiquadFilter();
      const gain = context.createGain();
      const pan = context.createStereoPanner();
      paper.buffer = buffer;
      filter.type = "bandpass";
      filter.Q.value = 0.65;
      const now = context.currentTime;
      filter.frequency.setValueAtTime(800, now);
      filter.frequency.exponentialRampToValueAtTime(2600, now + 0.22);
      filter.frequency.exponentialRampToValueAtTime(500, now + duration);
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.exponentialRampToValueAtTime(0.3, now + 0.16);
      gain.gain.exponentialRampToValueAtTime(0.06, now + 0.38);
      gain.gain.exponentialRampToValueAtTime(0.2, now + 0.52);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
      pan.pan.setValueAtTime(backwards ? 0.85 : -0.85, now);
      pan.pan.linearRampToValueAtTime(backwards ? -0.85 : 0.85, now + duration);
      paper
        .connect(filter)
        .connect(gain)
        .connect(pan)
        .connect(context.destination);
      paper.onended = () => {
        paper.disconnect();
        filter.disconnect();
        gain.disconnect();
        pan.disconnect();
        if (source.current === paper) source.current = null;
      };
      source.current = paper;
      paper.start();
    } catch {
      // Missing/blocked audio must never prevent opening a version.
    }
  };
  return {
    turn,
    soundEnabled,
    toggleSound: () => {
      enabled.current = !soundEnabled;
      setSoundEnabled(enabled.current);
      source.current?.stop();
    },
    beginTurn: (from: number, to: number) => {
      enabled.current = soundEnabled;
      if (from === to || reducedMotion()) return;
      setTurn({ key: ++serial.current, from, to, backwards: to < from });
      if (soundEnabled) void playPaper(to < from);
    },
  };
}

export function ArchivePageTurn({ turn }: { turn: PageTurn | null }) {
  if (!turn) return null;
  return createPortal(
    <div
      key={turn.key}
      className={`archive-page-turn ${turn.backwards ? "backwards" : "forwards"}`}
      aria-hidden="true"
    >
      <div className="turn-ambient-shadow" />
      {[0, 1, 2].map((leaf) => (
        <div
          className="turn-leaf"
          key={leaf}
          style={{ "--leaf": leaf } as CSSProperties}
        >
          <div className="turn-paper-face">
            <span className="turn-paper-border" />
            <span className="turn-paper-brand">
              ONCE WRONG<span>版本檔案館</span>
            </span>
            <span className="turn-paper-title">
              {turn.backwards ? "溯 卷" : "續 卷"}
            </span>
            <span className="turn-paper-number">
              第 {turn.from} 卷 <i>／</i> 第 {turn.to} 卷
            </span>
            <span className="turn-paper-rule" />
            <span className="turn-paper-caption">每一次修訂，皆有跡可循。</span>
          </div>
        </div>
      ))}
    </div>,
    document.body,
  );
}
