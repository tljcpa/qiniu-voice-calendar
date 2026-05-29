// Azure Speech 浏览器端语音合成（TTS）hook。
//
// 闭环关键（见复盘 D-03）：助手生成回应文案后朗读出来，形成真"语音对话"而非仅语音输入。
// 用后端短时 token 直连 Azure 合成并播放，key 不下发前端。
import { useRef, useState } from "react";
import * as SpeechSDK from "microsoft-cognitiveservices-speech-sdk";
import { fetchSpeechToken } from "../api/client";

const VOICE = "zh-CN-XiaoxiaoNeural"; // 自然女声，中文 demo 常用

export function useSpeechSynthesis() {
  const [speaking, setSpeaking] = useState(false);
  // 静音开关：默认开启朗读（闭环卖点），用户可关
  const [enabled, setEnabled] = useState(true);
  const synthRef = useRef<SpeechSDK.SpeechSynthesizer | null>(null);

  function toggleEnabled() {
    setEnabled((v) => {
      const next = !v;
      if (!next) {
        // 关闭时立即停掉正在进行的合成
        stop();
      }
      return next;
    });
  }

  function stop() {
    const s = synthRef.current;
    if (s) {
      s.close();
      synthRef.current = null;
    }
    setSpeaking(false);
  }

  async function speak(text: string) {
    if (!enabled || !text) {
      return;
    }
    try {
      const { token, region } = await fetchSpeechToken();
      const speechConfig = SpeechSDK.SpeechConfig.fromAuthorizationToken(
        token,
        region
      );
      speechConfig.speechSynthesisVoiceName = VOICE;
      // 默认扬声器输出；浏览器里即播放。
      const synthesizer = new SpeechSDK.SpeechSynthesizer(speechConfig);
      synthRef.current = synthesizer;
      setSpeaking(true);
      synthesizer.speakTextAsync(
        text,
        () => {
          synthesizer.close();
          synthRef.current = null;
          setSpeaking(false);
        },
        () => {
          // 合成失败不致命：文字回应已展示
          synthesizer.close();
          synthRef.current = null;
          setSpeaking(false);
        }
      );
    } catch {
      setSpeaking(false);
    }
  }

  return { speaking, enabled, toggleEnabled, speak, stop };
}
