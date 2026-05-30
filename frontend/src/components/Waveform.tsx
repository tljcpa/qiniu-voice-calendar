import { useEffect, useRef } from "react";

interface Props {
  active: boolean;
}

/**
 * 录音波形：录音时用 Web Audio AnalyserNode 实时绘制麦克风电平细条。
 * 单一强调色（非渐变），克制。拿不到麦克风时回退轻微摆动占位。
 */
export default function Waveform({ active }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);

  useEffect(() => {
    if (!active) {
      cleanup();
      return;
    }

    let analyser: AnalyserNode | null = null;
    let dataArray: Uint8Array<ArrayBuffer> | null = null;
    let phase = 0;
    let cancelled = false;

    async function setup() {
      const canvas = canvasRef.current;
      if (!canvas) {
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const AudioCtx =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext: typeof AudioContext })
            .webkitAudioContext;
        const audioCtx = new AudioCtx();
        ctxRef.current = audioCtx;
        const source = audioCtx.createMediaStreamSource(stream);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 64;
        source.connect(analyser);
        dataArray = new Uint8Array(analyser.frequencyBinCount);
      } catch {
        analyser = null;
      }

      const draw = () => {
        const c = canvasRef.current;
        const g = c?.getContext("2d");
        if (!c || !g) {
          return;
        }
        const w = c.width;
        const h = c.height;
        g.clearRect(0, 0, w, h);
        const bars = 32;
        const gap = 2;
        const barW = (w - gap * (bars - 1)) / bars;
        g.fillStyle = "#e2a749"; // 蜜琥珀强调色

        for (let i = 0; i < bars; i++) {
          let v: number;
          if (analyser && dataArray) {
            analyser.getByteFrequencyData(dataArray);
            const idx = Math.floor((i / bars) * dataArray.length);
            v = dataArray[idx] / 255;
          } else {
            v = 0.15 + 0.2 * Math.abs(Math.sin(phase + i * 0.4));
          }
          const barH = Math.max(2, v * h);
          const x = i * (barW + gap);
          const y = (h - barH) / 2;
          g.fillRect(x, y, barW, barH);
        }
        phase += 0.12;
        rafRef.current = requestAnimationFrame(draw);
      };
      draw();
    }

    setup();
    return () => {
      cancelled = true;
      cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  function cleanup() {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (ctxRef.current) {
      ctxRef.current.close().catch(() => {});
      ctxRef.current = null;
    }
  }

  if (!active) {
    return null;
  }
  return <canvas ref={canvasRef} width={220} height={28} aria-hidden="true" />;
}
