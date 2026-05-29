// Azure Speech 浏览器端语音识别 hook。
//
// 流程（见复盘 D-02）：从后端 /api/speech/token 取短时令牌 → 用令牌初始化 SDK →
// 默认麦克风 + zh-CN → recognizeOnceAsync 识别一句话，识别中通过 recognizing 实时回显。
// 令牌不接触订阅 key，识别直连 Azure（低延迟、可流式回显）。
import { useRef, useState } from "react";
import * as SpeechSDK from "microsoft-cognitiveservices-speech-sdk";
import { fetchSpeechToken } from "../api/client";

interface Callbacks {
  onInterim: (text: string) => void;
  onFinal: (text: string) => void;
  onError: (msg: string) => void;
}

export function useSpeechRecognition() {
  const [listening, setListening] = useState(false);
  const [supported] = useState(() => {
    // 浏览器需支持麦克风采集
    return typeof navigator !== "undefined" && !!navigator.mediaDevices;
  });
  const recognizerRef = useRef<SpeechSDK.SpeechRecognizer | null>(null);

  async function start(cb: Callbacks) {
    if (listening) {
      return;
    }
    try {
      const { token, region } = await fetchSpeechToken();
      const speechConfig = SpeechSDK.SpeechConfig.fromAuthorizationToken(
        token,
        region
      );
      speechConfig.speechRecognitionLanguage = "zh-CN";
      const audioConfig = SpeechSDK.AudioConfig.fromDefaultMicrophoneInput();
      const recognizer = new SpeechSDK.SpeechRecognizer(
        speechConfig,
        audioConfig
      );
      recognizerRef.current = recognizer;

      // 识别中：实时回显（流式文本）
      recognizer.recognizing = (_s, e) => {
        if (e.result.text) {
          cb.onInterim(e.result.text);
        }
      };

      setListening(true);
      recognizer.recognizeOnceAsync(
        (result) => {
          setListening(false);
          recognizer.close();
          recognizerRef.current = null;
          if (result.reason === SpeechSDK.ResultReason.RecognizedSpeech) {
            cb.onFinal(result.text);
          } else if (result.reason === SpeechSDK.ResultReason.NoMatch) {
            cb.onError("没听清，请再说一次");
          } else {
            cb.onError("识别未完成");
          }
        },
        (err) => {
          setListening(false);
          recognizer.close();
          recognizerRef.current = null;
          cb.onError(`识别失败：${err}`);
        }
      );
    } catch (err) {
      setListening(false);
      cb.onError(`无法启动语音识别：${err}`);
    }
  }

  function stop() {
    const recognizer = recognizerRef.current;
    if (recognizer) {
      recognizer.close();
      recognizerRef.current = null;
    }
    setListening(false);
  }

  return { listening, supported, start, stop };
}
