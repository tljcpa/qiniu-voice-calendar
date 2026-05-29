// Azure Speech 浏览器端语音识别 hook，带浏览器原生 Web Speech API 降级。
//
// 主路径（见复盘 D-02）：后端 /api/speech/token 取短时令牌 → Azure SDK → zh-CN →
// recognizeOnceAsync，识别中实时回显。令牌不接触订阅 key。
// 降级路径：Azure 令牌不可用（后端 503 / 网络问题）时，回退到浏览器原生
// SpeechRecognition——保证"工业级优先、原生兜底"，落地 README 声称的可降级。
import { useRef, useState } from "react";
import * as SpeechSDK from "microsoft-cognitiveservices-speech-sdk";
import { fetchSpeechToken } from "../api/client";

interface Callbacks {
  onInterim: (text: string) => void;
  onFinal: (text: string) => void;
  onError: (msg: string) => void;
}

// 浏览器原生 Web Speech API 的最小类型（标准库未内置）
interface WebSpeechResult {
  isFinal: boolean;
  0: { transcript: string };
}
interface WebSpeechEvent {
  resultIndex: number;
  results: { length: number; [i: number]: WebSpeechResult };
}
interface WebSpeechRecognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: WebSpeechEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

function getWebSpeechCtor(): (new () => WebSpeechRecognition) | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => WebSpeechRecognition;
    webkitSpeechRecognition?: new () => WebSpeechRecognition;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function useSpeechRecognition() {
  const [listening, setListening] = useState(false);
  // 当前识别引擎：azure / web（降级）/ null
  const [engine, setEngine] = useState<"azure" | "web" | null>(null);
  const [supported] = useState(() => {
    if (typeof navigator !== "undefined" && navigator.mediaDevices) {
      return true;
    }
    // 没有 mediaDevices 但有原生识别，也算支持
    return getWebSpeechCtor() !== null;
  });
  const recognizerRef = useRef<SpeechSDK.SpeechRecognizer | null>(null);
  const webRef = useRef<WebSpeechRecognition | null>(null);

  function startWebSpeech(cb: Callbacks) {
    const Ctor = getWebSpeechCtor();
    if (!Ctor) {
      setListening(false);
      cb.onError("语音识别不可用，请用文字输入");
      return;
    }
    const rec = new Ctor();
    webRef.current = rec;
    rec.lang = "zh-CN";
    rec.interimResults = true;
    rec.continuous = false;
    setEngine("web");
    setListening(true);

    rec.onresult = (e) => {
      let interim = "";
      let final = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) {
          final += r[0].transcript;
        } else {
          interim += r[0].transcript;
        }
      }
      if (interim) {
        cb.onInterim(interim);
      }
      if (final) {
        cb.onFinal(final);
      }
    };
    rec.onerror = (ev) => {
      setListening(false);
      webRef.current = null;
      cb.onError(`识别失败：${ev.error}`);
    };
    rec.onend = () => {
      setListening(false);
      webRef.current = null;
    };
    rec.start();
  }

  async function start(cb: Callbacks) {
    if (listening) {
      return;
    }
    // 主路径：Azure。取不到令牌则降级到浏览器原生。
    let token: string;
    let region: string;
    try {
      const t = await fetchSpeechToken();
      token = t.token;
      region = t.region;
    } catch {
      // 降级
      startWebSpeech(cb);
      return;
    }

    try {
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
      setEngine("azure");

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
    const web = webRef.current;
    if (web) {
      web.stop();
      webRef.current = null;
    }
    setListening(false);
  }

  return { listening, supported, engine, start, stop };
}
