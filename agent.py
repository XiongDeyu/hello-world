import argparse
import json
import os
import re
from typing import Dict, List, Optional, Tuple

import requests
from openai import OpenAI

SYSTEM_PROMPT = """# Role (角色)
你是一个专业的「加密货币研究助手」 (Crypto Research Assistant)。你的主要职责是为用户在复杂多变的加密货币市场中，寻找准确、最新、客观的信息，并将这些信息进行清晰、结构化的总结。

# Objective (目标)
1. 快速检索和分析加密货币项目的基础面、代币经济学、链上数据、市场表现及最新新闻。
2. 过滤噪音，剔除没有根据的喊单（Shilling）和 FUD，只提供基于事实和数据的准确信息。
3. 将复杂的信息提炼为清晰易读的摘要，帮助用户快速做出研究判断。
4. 【核心目标】确保每一项数据和陈述都有明确的来源，做到 100% 信息可溯源。

# Tone & Style (基调与风格)
- 客观、中立、专业、严谨。
- 免责声明：始终保持中立态度，绝对不提供任何形式的财务或投资建议（NFA - Not Financial Advice）。当用户询问“是否该买入/卖出”时，必须提醒用户自行承担风险（DYOR）。

# Workflow (工作流程)
当你收到用户的查询请求时，请遵循以下步骤：
1. 意图分析：明确用户是想了解特定代币、特定赛道、近期新闻，还是具体的链上数据。
2. 数据检索：必须调用指定的工具/API/搜索引擎获取实时数据。
3. 结构化输出：请严格按以下结构输出你的回答：
   - 📌 一句话总结：[对该项目/事件的极简概括]
   - 📊 核心数据：[当前价格、市值、24小时交易量等，必须在数据后用括号标注来源]
   - 📝 关键信息分析：[分点列出机制或新闻，每一条重要陈述都必须附带来源链接]
   - 📰 近期动态/情绪：[近期重要新闻，需带新闻出处]
   - 🔗 参考文献与链接：[强制罗列本次回答使用的所有数据源、文章链接或 API 名称，不可省略]

# Rules & Constraints (绝对不可违反的规则)
1. 【零猜测原则】：严禁凭空捏造（幻觉）任何价格、市值、TVL、解锁时间或新闻事件。如果通过工具和搜索没有找到确切的数据，你必须如实回答：“我目前无法通过可靠工具找到相关确切数据。”绝对不允许使用“可能是”、“大概是”、“据推测”来伪造数据。
2. 【强制引用原则】：你提供的每一个数字、每一条新闻、每一段项目机制的解释，都必须有明确的来源支撑。在行文中使用 Markdown 链接格式 [来源名称](URL) 进行内联引用。
3. 【防过时原则】：加密市场变化极快，如果你的底层知识库信息早于当前日期，必须优先使用外部工具（Search/API）获取最新情况。
4. 【通俗化表达】：解释专业术语（如 TVL, AMM, ZK-Rollup）时，用大白话或类比，让非技术人员也能听懂，但通俗化解释不能偏离技术白皮书的原始定义（需引用白皮书或官方文档）。
"""

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_KIMI_MODEL = "moonshot-v1-8k"
DEFAULT_KIMI_BASE_URL = "https://api.moonshot.cn/v1"

COIN_HINTS = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "etherum": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
    "pepe": "pepe",
    "tia": "celestia",
    "celestia": "celestia",
}


def detect_coin_id(question: str) -> Optional[str]:
    lowered = question.lower()
    for hint, coin_id in COIN_HINTS.items():
        if re.search(rf"\b{re.escape(hint)}\b", lowered):
            return coin_id
    return None


def needs_price_lookup(question: str) -> bool:
    lowered = question.lower()
    keywords = [
        "price",
        "价格",
        "市值",
        "多少钱",
        "quote",
        "行情",
        "涨",
        "跌",
    ]
    return any(k in lowered for k in keywords)


def get_coin_price(coin_id: str, vs_currency: str = "usd") -> Dict:
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": vs_currency,
        "include_market_cap": "true",
        "include_24hr_vol": "true",
        "include_24hr_change": "true",
        "include_last_updated_at": "true",
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if coin_id not in payload:
        raise ValueError("CoinGecko 未返回该代币的可用数据")

    source_url = f"{url}?ids={coin_id}&vs_currencies={vs_currency}&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true&include_last_updated_at=true"
    return {
        "coin_id": coin_id,
        "vs_currency": vs_currency,
        "price_data": payload[coin_id],
        "sources": [
            {
                "name": "CoinGecko Simple Price API",
                "url": source_url,
            }
        ],
    }


def build_user_prompt(question: str, market_context: Optional[Dict]) -> str:
    if market_context is None:
        context_text = (
            "未查询到外部实时数据。请明确告诉用户："
            "我目前无法通过可靠工具找到相关确切数据。"
        )
    else:
        context_text = (
            "以下是经过工具查询的实时数据（可引用）：\n"
            f"```json\n{json.dumps(market_context, ensure_ascii=False, indent=2)}\n```"
        )

    return (
        f"用户问题：{question}\n\n"
        f"工具上下文：\n{context_text}\n\n"
        "请使用中文输出，且严格按系统要求的结构化格式回复，并强制内联引用来源。"
    )


def ensure_reference_section(answer: str, sources: List[Dict]) -> str:
    has_reference = "参考文献" in answer or "参考资料" in answer
    has_link = bool(re.search(r"https?://", answer))
    if has_reference and has_link:
        return answer

    references = "\n".join(
        [f"- [{item['name']}]({item['url']})" for item in sources if item.get("url")]
    )
    suffix = "\n\n🔗 **参考文献与链接**\n" + (references or "- 无可用来源")
    return answer + suffix


def resolve_llm_client(model_override: Optional[str]) -> Tuple[Optional[OpenAI], Optional[str], str]:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    openai_key = os.getenv("OPENAI_API_KEY")
    kimi_key = os.getenv("KIMI_API_KEY")

    if provider in {"kimi", "moonshot"}:
        if not kimi_key:
            return None, None, "kimi"
        base_url = os.getenv("KIMI_BASE_URL", DEFAULT_KIMI_BASE_URL)
        model = model_override or os.getenv("KIMI_MODEL", DEFAULT_KIMI_MODEL)
        return OpenAI(api_key=kimi_key, base_url=base_url), model, "kimi"

    if openai_key:
        model = model_override or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        return OpenAI(api_key=openai_key), model, "openai"

    if kimi_key:
        base_url = os.getenv("KIMI_BASE_URL", DEFAULT_KIMI_BASE_URL)
        model = model_override or os.getenv("KIMI_MODEL", DEFAULT_KIMI_MODEL)
        return OpenAI(api_key=kimi_key, base_url=base_url), model, "kimi"

    return None, None, "none"


def missing_key_message(provider: str) -> str:
    if provider == "kimi":
        return "缺少 KIMI_API_KEY"
    if provider == "openai":
        return "缺少 OPENAI_API_KEY"
    return "缺少 OPENAI_API_KEY 或 KIMI_API_KEY"


def run_agent(question: str, model_override: Optional[str]) -> str:
    market_context = None
    sources: List[Dict] = []

    if needs_price_lookup(question):
        coin_id = detect_coin_id(question)
        if coin_id:
            try:
                market_context = get_coin_price(coin_id)
                sources = market_context.get("sources", [])
            except (requests.RequestException, ValueError):
                market_context = None

    client, model, provider = resolve_llm_client(model_override)
    if client is None or model is None:
        data_line = "- 未查询到可靠的实时价格数据。"
        if market_context is not None:
            data_line = f"- 已查询 {market_context['coin_id']} 实时数据：`{json.dumps(market_context['price_data'], ensure_ascii=False)}`"
        fallback = (
            "📌 **一句话总结**\n"
            "我目前无法完成完整 LLM 分析，但可以返回已查询到的数据。\n\n"
            "📊 **核心数据**\n"
            f"{data_line}\n\n"
            "📝 **关键信息分析**\n"
            f"- 若需完整分析，请配置 API Key（{missing_key_message(provider)}）后重试。\n\n"
            "📰 **近期动态/情绪**\n"
            "- 当前 MVP 未接入新闻 API。\n"
        )
        return ensure_reference_section(fallback, sources)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(question, market_context)},
        ],
    )
    output_text = (response.choices[0].message.content or "").strip()
    return ensure_reference_section(output_text, sources)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crypto Research Assistant MVP")
    parser.add_argument("question", help="用户问题，例如：帮我看下 BTC 现在价格")
    parser.add_argument(
        "--model",
        default=None,
        help="模型名称（用于覆盖环境变量默认值）",
    )

    args = parser.parse_args()
    result = run_agent(args.question, args.model)
    print(result)


if __name__ == "__main__":
    main()
