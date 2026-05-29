// 前端轻量意图判定：冲突反问后，把用户回复分类为 接受建议 / 坚持原时间 / 其它。
// 纯函数，便于单测。其它（other）由调用方当作全新指令处理。

// 接受建议（改到系统给的时间）
const AFFIRM_WORDS = [
  "好",
  "好的",
  "行",
  "可以",
  "改吧",
  "换吧",
  "同意",
  "没问题",
  "听你的",
  "嗯",
  "对",
];

// 坚持原时间（明知冲突也要原时间）
const INSIST_WORDS = [
  "就这个",
  "就用",
  "不改",
  "不用改",
  "不换",
  "还是原来",
  "坚持",
  "就原",
];

export type ConflictReply = "accept" | "insist" | "other";

function matchAny(text: string, words: string[]): boolean {
  return words.some((w) => text.includes(w));
}

/**
 * 分类冲突反问的回复。先判坚持（更具体），再判接受，都不是则 other。
 */
export function classifyConflictReply(text: string): ConflictReply {
  if (matchAny(text, INSIST_WORDS)) {
    return "insist";
  }
  if (matchAny(text, AFFIRM_WORDS)) {
    return "accept";
  }
  return "other";
}
