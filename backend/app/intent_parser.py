"""意图解析与实体抽取。

把用户的自由口语指令（ASR 识别出的文本）解析成结构化意图与槽位，
供下游时间解析（PR6）、冲突检测（PR8）、日历 CRUD（PR7）使用。

设计（见 docs/复盘.md D-05、D-15）：
- 意图 5 类 + 兜底：add / delete / view / update / clarify / unknown。
- 用 LLM 的 JSON mode 强约束输出 schema；带 few-shot 稳定口语变体归类。
- LLM 只抽**原始时间表达 time_expr**，不做时间归一化——归一化是 time_parser 的职责。
- 数值/可选槽位缺失一律给 null/空，宁可后续追问也不臆测，避免幻觉填充错误日程。
"""

from typing import Optional

from app.llm_provider import LLMProvider, get_llm

# 允许的意图集合。LLM 返回集合外的值一律归 unknown。
ALLOWED_INTENTS = {"add", "delete", "view", "update", "clarify", "plan", "unknown"}


INTENT_SYSTEM_PROMPT = """\
你是语音日历助手的意图解析器。用户通过语音说出日历操作指令，你把它解析为严格的 JSON。

只输出一个 JSON 对象，字段如下（缺失项按规则填默认值，不要臆测）：
{
  "intent": "add | delete | view | update | clarify | plan | unknown",
  "confidence": 0~1 的小数，你对该意图判断的把握,
  "title": "事件标题，如'产品评审会'；无则 null",
  "plan_items": "intent=plan 时，把目标拆成多个待安排事件的数组，每项 {\\"title\\":\\"...\\",\\"time_expr\\":\\"该项的大致时间原文，如'下周一下午'\\",\\"duration_minutes\\":时长整数}；其它意图为 null",
  "time_expr": "用户说的原始时间表达原文，如'明天下午三点''下周一九点半'；不要换算成日期，无则 null",
  "location": "地点，无则 null",
  "attendees": ["参与人列表，无则空数组"],
  "reminder_before_minutes": 提前提醒分钟数的整数，用户没说则 null,
  "target_query": "删除/修改/查询时用来定位目标事件的描述，如'我的会''下午那个'；add 时为 null",
  "new_values": {"修改时的新值，如 {\\"time_expr\\":\\"四点\\"}；其它意图为 null 或不含此键"},
  "clarification": "当 intent=clarify 时，要反问用户的问题；否则 null",
  "missing": ["关键槽位缺失项，如 ['time'] ['target']；不缺为空数组"]
}

判定规则：
- 添加/新建/安排/记一下/提醒我 → add。
- 删除/取消/删掉/不要了/去掉 → delete。
- 查/看/有什么安排/几点/今天忙吗 → view。
- 改/挪/推迟/提前/换成/改到 → update。
- 删除/修改时：只要用户给出了**具体的事件名称或描述**（如"客户对接""羽毛球""产品评审会"），
  即使你不知道库里是否存在、有几个，也要返回 delete/update，把该描述放进 target_query，
  由系统查库决定要不要澄清。不要替系统编造"你有多个X"这类你无法知道的事实。
- 仅当用户用**纯指代且没有任何具体名称**（如"那个""刚才那个""之前那个"）→ clarify。
- add 缺时间也用 clarify，在 clarification 写要追问的话，missing 列缺失槽位。
- **多事件规划目标** → plan：当用户给的是一个需要拆成**多个**日程的目标（如"下周安排三场论文复习""这周想健身三次每次一小时""帮我规划周末两天的复习"），
  返回 intent=plan，并在 plan_items 里给出每一项的 {title, time_expr, duration_minutes}。
  各项 time_expr 给不同的大致时段（分散开，便于避免互相冲突），duration_minutes 按用户说的时长或默认 60。
- 与日历无关或完全听不懂 → unknown。
- time_expr 必须是用户原话里的时间短语，禁止你自己换算成具体日期。

few-shot 示例：
用户：明天下午三点开产品评审会，叫上小王
输出：{"intent":"add","confidence":0.95,"title":"产品评审会","time_expr":"明天下午三点","location":null,"attendees":["小王"],"reminder_before_minutes":null,"target_query":null,"new_values":null,"clarification":null,"missing":[]}

用户：把我下午的客户对接往后挪一小时
输出：{"intent":"update","confidence":0.9,"title":null,"time_expr":null,"location":null,"attendees":[],"reminder_before_minutes":null,"target_query":"下午的客户对接","new_values":{"shift":"往后一小时"},"clarification":null,"missing":[]}

用户：今天有什么安排
输出：{"intent":"view","confidence":0.95,"title":null,"time_expr":"今天","location":null,"attendees":[],"reminder_before_minutes":null,"target_query":null,"new_values":null,"clarification":null,"missing":[]}

用户：把客户对接删了
输出：{"intent":"delete","confidence":0.92,"title":null,"time_expr":null,"location":null,"attendees":[],"reminder_before_minutes":null,"target_query":"客户对接","new_values":null,"clarification":null,"missing":[]}

用户：把那个删了
输出：{"intent":"clarify","confidence":0.5,"title":null,"time_expr":null,"location":null,"attendees":[],"reminder_before_minutes":null,"target_query":"那个","new_values":null,"clarification":"你指的是哪个日程？","missing":["target"]}

用户：帮我加个会
输出：{"intent":"clarify","confidence":0.7,"title":"会","time_expr":null,"location":null,"attendees":[],"reminder_before_minutes":null,"target_query":null,"new_values":null,"clarification":"这个会安排在什么时间？","missing":["time"]}

用户：帮我安排下周三场论文复习，每次两小时，避开已有的会
输出：{"intent":"plan","confidence":0.9,"title":null,"time_expr":null,"location":null,"attendees":[],"reminder_before_minutes":null,"target_query":null,"new_values":null,"clarification":null,"missing":[],"plan_items":[{"title":"论文复习","time_expr":"下周一下午两点","duration_minutes":120},{"title":"论文复习","time_expr":"下周三下午两点","duration_minutes":120},{"title":"论文复习","time_expr":"下周五下午两点","duration_minutes":120}]}
"""


def _normalize(raw: dict) -> dict:
    """把 LLM 返回的原始 dict 规整成稳定结构，补默认值、校验意图。"""
    result: dict = {}

    intent = raw.get("intent")
    if intent not in ALLOWED_INTENTS:
        intent = "unknown"
    result["intent"] = intent

    # confidence 容错为 0~1 浮点
    confidence = raw.get("confidence")
    if isinstance(confidence, (int, float)):
        result["confidence"] = float(confidence)
    else:
        result["confidence"] = 0.0

    result["title"] = raw.get("title") or None
    result["time_expr"] = raw.get("time_expr") or None
    result["location"] = raw.get("location") or None

    attendees = raw.get("attendees")
    if isinstance(attendees, list):
        result["attendees"] = [str(a) for a in attendees]
    else:
        result["attendees"] = []

    reminder = raw.get("reminder_before_minutes")
    if isinstance(reminder, int):
        result["reminder_before_minutes"] = reminder
    else:
        result["reminder_before_minutes"] = None

    result["target_query"] = raw.get("target_query") or None

    new_values = raw.get("new_values")
    if isinstance(new_values, dict):
        result["new_values"] = new_values
    else:
        result["new_values"] = None

    result["clarification"] = raw.get("clarification") or None

    missing = raw.get("missing")
    if isinstance(missing, list):
        result["missing"] = [str(m) for m in missing]
    else:
        result["missing"] = []

    # 规划项（intent=plan）：规整为干净的 {title,time_expr,duration_minutes} 列表
    plan_items = raw.get("plan_items")
    clean_items = []
    if isinstance(plan_items, list):
        for it in plan_items:
            if not isinstance(it, dict):
                continue
            title = it.get("title") or "日程"
            time_expr = it.get("time_expr")
            if not time_expr:
                continue
            dur = it.get("duration_minutes")
            if not isinstance(dur, int) or dur <= 0:
                dur = 60
            clean_items.append(
                {"title": str(title), "time_expr": str(time_expr), "duration_minutes": dur}
            )
    result["plan_items"] = clean_items

    return result


def parse_intent(
    text: str,
    now_iso: Optional[str] = None,
    llm: Optional[LLMProvider] = None,
) -> dict:
    """解析一句话指令为结构化意图。

    参数：
        text: ASR 识别出的用户原话。
        now_iso: 当前时间 ISO8601，作为上下文帮助 LLM 理解相对表达（不做归一化）。
        llm: LLM provider，默认取全局单例；测试时注入假对象。

    返回：规整后的意图 dict（结构见 _normalize）。
    """
    if llm is None:
        llm = get_llm()

    user_content = text
    if now_iso is not None:
        user_content = f"（当前时间：{now_iso}）\n用户：{text}"

    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    raw = llm.complete_json(messages, temperature=0.1, max_tokens=512)
    return _normalize(raw)
