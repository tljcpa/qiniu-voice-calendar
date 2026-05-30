// API 客户端单元测试：mock 全局 fetch，验证 URL 构建 / 请求体 / 错误处理。
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchEvents,
  resolveCommand,
  sendCommand,
  fetchSpeechToken,
} from "./client";

function mockFetch(body: unknown, ok = true, status = 200) {
  const fn = vi.fn(async () => {
    return {
      ok,
      status,
      json: async () => body,
      text: async () => JSON.stringify(body),
    } as Response;
  });
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("fetchEvents", () => {
  it("无范围时请求 /api/events", async () => {
    const fn = mockFetch([]);
    await fetchEvents();
    expect(fn.mock.calls[0][0]).toBe("/api/events");
  });

  it("带范围时拼 query", async () => {
    const fn = mockFetch([]);
    await fetchEvents("2026-05-30T00:00:00", "2026-05-30T23:59:59");
    const url = fn.mock.calls[0][0] as string;
    expect(url).toContain("/api/events?");
    expect(url).toContain("start=");
    expect(url).toContain("end=");
  });
});

describe("sendCommand", () => {
  it("POST /api/voice/command，body 含 text 与 force=false", async () => {
    const fn = mockFetch({ intent: "view", ok: true });
    await sendCommand("今天有什么安排");
    const [url, init] = fn.mock.calls[0];
    expect(url).toBe("/api/voice/command");
    expect(init.method).toBe("POST");
    const payload = JSON.parse(init.body as string);
    expect(payload.text).toBe("今天有什么安排");
    expect(payload.force).toBe(false);
  });

  it("force=true 透传", async () => {
    const fn = mockFetch({ ok: true });
    await sendCommand("就用这个时间", true);
    const payload = JSON.parse(fn.mock.calls[0][1].body as string);
    expect(payload.force).toBe(true);
  });
});

describe("resolveCommand", () => {
  it("POST /api/voice/resolve，带 intent/candidates/new_values", async () => {
    const fn = mockFetch({ ok: true });
    const cands = [{ id: 1, title: "会", start_at: "2026-05-30T15:00:00" }];
    await resolveCommand("第一个", "delete", cands as never, null);
    const [url, init] = fn.mock.calls[0];
    expect(url).toBe("/api/voice/resolve");
    const payload = JSON.parse(init.body as string);
    expect(payload.intent).toBe("delete");
    expect(payload.candidates).toHaveLength(1);
    expect(payload.new_values).toBeNull();
  });
});

describe("错误处理", () => {
  it("非 2xx 抛错", async () => {
    mockFetch({ detail: "boom" }, false, 503);
    await expect(fetchSpeechToken()).rejects.toThrow(/API 503/);
  });
});
