"""AI Parser 接口模块

当前为占位实现 (返回 None)。
未来接入 DeepSeek/Qwen/GPT/Claude 时：
  1. 设置环境变量 AI_API_KEY
  2. 实现下方的 _call_ai_api() 函数
  3. 在 sites_config.json 中设置 "ai_enabled": true

接口规范：
  parse_with_ai(html, site_cfg=None) -> dict or None
  返回格式: {
    "title": str,
    "content": str,
    "publish_date": str,
    "source": str,
  }
"""

import logging
log = logging.getLogger('crawler.ai_parser')


def _call_ai_api(prompt, html, max_tokens=2000):
    """调用 AI API 的底层函数 (当前未实现)。
    接入示例:
        import openai
        client = openai.OpenAI(api_key=os.environ["AI_API_KEY"])
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": "你是正文提取助手。从HTML中提取标题和正文。返回JSON格式。"
            }, {
                "role": "user",
                "content": prompt
            }],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    """
    log.warning("AI API not configured. Set AI_API_KEY env to enable.")
    return None


def parse_with_ai(html, site_cfg=None):
    """AI 正文提取接口。返回 dict 或 None。
    
    当前为占位实现。接入 LLM 后，main.py 与 dispatcher.py 无需任何修改。
    """
    if not html or len(html) < 100:
        return None
    
    # 检查是否启用 AI
    if site_cfg and site_cfg.get('extract', {}).get('ai_enabled'):
        log.info("AI parser enabled for %s", site_cfg.get('name', 'unknown'))
        
        prompt = f"""请从以下HTML中提取正文内容，返回干净的JSON格式:
{{
  "title": "文章标题",
  "content": "正文内容(去除HTML标签)",
  "publish_date": "发布日期(YYYY-MM-DD格式，如无则为空)"
}}

HTML内容(前3000字符):
{html[:3000]}"""

        result = _call_ai_api(prompt, html)
        if result:
            import json
            try:
                return json.loads(result)
            except:
                log.warning("AI response not valid JSON, falling through")
    
    return None  # 未启用或未接入，返回 None 让下游 fallback
