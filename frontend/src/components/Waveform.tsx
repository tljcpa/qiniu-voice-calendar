import { useEffect, useRef } from "react";

interface Props {
  active: boolean;
}

/**
 * 语音波形动效：录音时用 Web Audio AnalyserNode 实时绘制麦克风频谱条，
 * 把"语音"卖点可视化。拿不到麦克风时回退为正弦摆动的占位动画。
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
    let dataArray: Uint8Array | null = null;
    let phase = 0;
    let cancelled = false;

    async function setup() {
      const canvas = canvasRef.current;
      if (!canvas) {
        return;
      }
      const g = canvas.getContext("2d");
      if (!g) {
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
        // 拿不到麦克风：保持 analyser 为空，draw 走占位动画
        analyser = null;
      }

      const draw = () => {
        const c = canvasRef.current;
        const gg = c?.getContext("2d");
        if (!c || !gg) {
          return;
        }
        const w = c.width;
        const h = c.height;
        gg.clearRect(0, 0, w, h);
        const bars = 28;
        const gap = 3;
        const barW = (w - gap * (bars - 1)) / bars;

        for (let i = 0; i < bars; i++) {
          let v: number;
          if (analyser && dataArray) {
            analyser.getByteFrequencyData(dataArray);
            const idx = Math.floor((i / bars) * dataArray.length);
            v = dataArray[idx] / 255;
          } else {
            // 占位：正弦波摆动
            v = 0.3 + 0.35 * Math.abs(Math.sin(phase + i * 0.4));
          }
          const barH = Math.max(3, v * h);
          const x = i * (barW + gap);
          const y = (h - barH) / 2;
          const grad = gg.createLinearGradient(0, y, 0, y + barH);
          grad.addColorStop(0, "#22d3ee");
          grad.addColorStop(1, "#a855f7");
          gg.fillStyle = grad;
          gg.beginPath();
          gg.roundRect(x, y, barW, barH, barW / 2);
          gg.fill();
        }
        phase += 0.15;
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
  return (
    <canvas
      ref={canvasRef}
      width={260}
      height={48}
      className="rounded-lg"
      aria-hidden="true"
    />
  );
}
