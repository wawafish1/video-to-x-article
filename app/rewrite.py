from __future__ import annotations

from typing import Any

import httpx
from openai import OpenAI

from .config import get_settings


TEMPLATES: dict[str, dict[str, str]] = {
    "market": {
        "label": "行情解读",
        "description": "适合币圈、股票、宏观、交易观点类视频。",
        "instruction": (
            "重点提炼行情背景、关键变量、可能催化、风险点和可验证数据。"
            "不要把预测写成确定事实，所有价格、时间、涨跌幅、项目名都放入待核查。"
        ),
    },
    "knowledge": {
        "label": "知识科普",
        "description": "适合方法论、概念解释、经验分享类视频。",
        "instruction": (
            "重点把口播内容整理成清晰的概念、步骤、例子和结论。"
            "语气要像 X 上可收藏的知识帖，少用夸张营销表达。"
        ),
    },
    "project": {
        "label": "项目介绍",
        "description": "适合产品、协议、工具、公司、项目介绍类视频。",
        "instruction": (
            "重点说明项目是什么、解决什么问题、核心亮点、适用人群、潜在风险。"
            "涉及融资、团队、生态、数据时必须列入待核查。"
        ),
    },
    "opinion": {
        "label": "观点评论",
        "description": "适合观点输出、热点评论、趋势判断类视频。",
        "instruction": (
            "重点提炼论点、论据、反方可能质疑和作者结论。"
            "表达要有态度，但避免攻击性和未经证实的断言。"
        ),
    },
    "news": {
        "label": "新闻快讯",
        "description": "适合新闻、公告、事件、政策更新类视频。",
        "instruction": (
            "重点提炼时间、地点、主体、事件、影响和后续观察点。"
            "所有事实性信息必须进入待核查清单，避免超出原稿的信息扩写。"
        ),
    },
}


DEFAULT_TEMPLATE = "market"


CLEAN_SYSTEM_PROMPT = """你是一个中文视频转写稿整理助手。
你的任务是把原始口播转写稿整理成更干净、更结构化的底稿。
只做清洗和结构化，不新增观点，不替作者补充原稿没有的信息。"""


ARTICLE_SYSTEM_PROMPT = """你是一个资深中文内容编辑，擅长把视频口播底稿改写成适合 X 平台发布的内容。
你的目标不是逐字搬运，而是保留核心观点、重组逻辑、提升可读性，并标出需要人工核查的信息。
如果内容涉及行情、投资、币圈、股票或宏观判断，必须加入风险提示，不能把预测写成确定事实。"""


def list_templates() -> list[dict[str, str]]:
    return [
        {"key": key, **value}
        for key, value in TEMPLATES.items()
    ]


def normalize_template_key(template_key: str | None) -> str:
    if template_key in TEMPLATES:
        return template_key
    return DEFAULT_TEMPLATE


def clean_transcript(raw_transcript: str, template_key: str | None = None) -> str:
    template = TEMPLATES[normalize_template_key(template_key)]
    prompt = f"""请整理下面的视频原始转写稿。

模板方向：{template["label"]}
额外注意：{template["instruction"]}

要求：
1. 删除明显口头禅、重复语气词、无意义停顿。
2. 修正明显的标点和分段问题。
3. 保留原始观点和信息，不要新增事实。
4. 将内容整理为适合二次编辑的中文底稿。
5. 对听不清、疑似识别错误、数字、时间、价格、人名、项目名，用 [待核查: ...] 标记。
6. 输出 Markdown，结构固定为：
# 清洗稿
# 关键信息
# 待核查点

原始转写稿：
---
{raw_transcript}
---"""
    cleaned = _chat_text(
        [
            {"role": "system", "content": CLEAN_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )
    return _ensure_heading(cleaned, "清洗稿")


def generate_article_bundle(cleaned_transcript: str, template_key: str | None = None) -> str:
    template = TEMPLATES[normalize_template_key(template_key)]
    prompt = f"""请基于下面的清洗稿，输出一份适合 X 发布的 Markdown 内容包。

内容模板：{template["label"]}
模板说明：{template["description"]}
写作要求：{template["instruction"]}

通用要求：
1. 不要逐字搬运原文，要重组表达。
2. 不要编造清洗稿没有的信息。
3. 开头要有吸引人的 hook，但不能标题党。
4. X Thread 最多 8 条，每条尽量短，适合直接复制发布。
5. 长文版要像完整文章，不要像转写稿。
6. 涉及投资、行情、政策或数据判断时，必须加风险提示。
7. 输出结构必须包含以下一级标题：
# 核心摘要
# X 单条短帖
# X Thread
# 长文版
# 待人工核查
# 风险提示

清洗稿：
---
{cleaned_transcript}
---"""
    article = _chat_text(
        [
            {"role": "system", "content": ARTICLE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )
    return _ensure_heading(article, "核心摘要")


def _chat_text(messages: list[dict[str, str]]) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY。请复制 .env.example 为 .env 并填写。")

    if settings.openai_base_url:
        return _chat_text_http(messages)
    return _chat_text_sdk(messages)


def _ensure_heading(markdown: str, heading: str) -> str:
    text = markdown.strip()
    if f"# {heading}" in text:
        return text
    return f"# {heading}\n\n{text}"


def _chat_text_http(messages: list[dict[str, str]]) -> str:
    settings = get_settings()
    base_url = settings.openai_base_url.rstrip("/")
    payload: dict[str, Any] = {
        "model": settings.text_model,
        "messages": messages,
    }

    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"].get("content", "")
    if not content:
        raise RuntimeError("文本模型返回为空。")
    return content.strip()


def _chat_text_sdk(messages: list[dict[str, str]]) -> str:
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    completion = client.chat.completions.create(
        model=settings.text_model,
        messages=messages,
    )
    content = completion.choices[0].message.content
    if not content:
        raise RuntimeError("文本模型返回为空。")
    return content.strip()
