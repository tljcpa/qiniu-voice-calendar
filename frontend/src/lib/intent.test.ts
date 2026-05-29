import { describe, expect, it } from "vitest";
import { classifyConflictReply } from "./intent";

describe("classifyConflictReply", () => {
  it("接受类回复 → accept", () => {
    for (const t of ["好", "好的", "可以", "改吧", "行", "听你的"]) {
      expect(classifyConflictReply(t)).toBe("accept");
    }
  });

  it("坚持类回复 → insist", () => {
    for (const t of ["就这个时间", "不改", "还是原来的", "坚持原时间"]) {
      expect(classifyConflictReply(t)).toBe("insist");
    }
  });

  it("坚持优先于接受（含'不改'即使含'改'）", () => {
    expect(classifyConflictReply("不改")).toBe("insist");
  });

  it("无关回复 → other（当作新指令）", () => {
    for (const t of ["明天下午三点开会", "今天有什么安排", "删掉那个"]) {
      expect(classifyConflictReply(t)).toBe("other");
    }
  });
});
