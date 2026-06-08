#!/usr/bin/env python3
"""
A股每日复盘推送 — 下午 15:30 发送
用 DeepSeek 生成自然语言分析，QQ邮箱 HTML 推送。
"""

import sys, os, json, logging, time
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

from stock_analyzer import (
    log, TRACKED_STOCKS, DEEPSEEK_API_KEY, DEEPSEEK_MODEL, EMAIL, TREND_COLORS,
    collect_all_data, analyze_all_stocks, build_stocks_brief,
    call_deepseek, send_email,
    fetch_index_data, fetch_market_stats, fetch_sector_flow, fetch_global_context,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ╔══════════════════════════════════════════════════════╗
# ║  复盘 DeepSeek Prompt                              ║
# ╚══════════════════════════════════════════════════════╝

def build_review_prompt(index_data, market_stats, sector_flow, global_ctx, stock_analyses):
    """构建复盘分析的 DeepSeek 请求"""
    indices_brief = {}
    for name, info in index_data.items():
        indices_brief[name] = {
            "latest": info.get("latest_close", info.get("latest", {}).get("close", "N/A")),
            "change_pct": info.get("change_pct", 0),
        }

    stocks_brief = build_stocks_brief(stock_analyses)

    payload = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "indices": indices_brief,
        "market": {
            "up_count": market_stats.get("up_count", 0),
            "down_count": market_stats.get("down_count", 0),
            "total_amount_yi": market_stats.get("total_amount_yi", 0),
        },
        "sector_flow": sector_flow[:5],
        "global": {
            "sp500": global_ctx.get("sp500"), "nasdaq": global_ctx.get("nasdaq"),
            "vix": global_ctx.get("vix"), "gold": global_ctx.get("gold"),
            "oil": global_ctx.get("oil"), "usd_cny": global_ctx.get("usd_cny"),
        },
        "stocks": stocks_brief,
    }

    system = """你是资深A股分析师。你的分析风格：简洁、客观、有洞察，不讲废话。

根据提供的今日市场数据、板块资金流向、全球背景和个股技术指标，生成一份复盘报告。

要求：
1. **大盘概况**：2-3句话，点出核心矛盾（涨跌、量能、指数分化）
2. **资金风向**：2-3句话，钱在往哪个方向走
3. **全球视角**：1-2句话，对A股的可能传导
4. **个股分析**：每只股票2-3句话，包含：
   - 当前趋势阶段判断和你的推理
   - 关键价位观察（支撑/压力）
   - 短期需要注意的风险或机会
5. **风险提示**：1句话总结当日最重要的风险

趋势阶段说明：
- 上升期：多头排列，趋势向上，适合持有
- 平稳期：无明显方向，观望为主
- 高位震荡期：价格处于高位区间，注意回调风险
- 回调期：价格从高位回落，关注支撑位是否有效
- 底部：价格处于低位，超卖区域，关注反转信号

只返回 JSON：
{
  "market_overview": "...",
  "fund_flow": "...",
  "global_view": "...",
  "stocks": [
    {"name": "长白山", "trend": "上升期", "analysis": "...", "key_level": "..."}
  ],
  "risk_warning": "..."
}"""

    user = f"今日市场数据：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    return system, user


# ╔══════════════════════════════════════════════════════╗
# ║  复盘邮件模板                                      ║
# ╚══════════════════════════════════════════════════════╝

def build_review_email(ai_result, stock_analyses):
    """构建复盘 HTML 邮件"""
    date_str = datetime.now().strftime("%Y年%m月%d日")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]

    stock_cards = ""
    for s in TRACKED_STOCKS:
        name, code = s["name"], s["code"]
        analysis = stock_analyses.get(name, {})
        ind = analysis.get("indicators", {})
        machine_trend = analysis.get("trend", "平稳期")
        machine_conf = analysis.get("confidence", 0)

        ai_trend = machine_trend
        ai_text = ""
        if ai_result:
            for ai_s in ai_result.get("stocks", []):
                if ai_s.get("name") == name:
                    ai_trend = ai_s.get("trend", machine_trend)
                    ai_text = ai_s.get("analysis", "")
                    break

        colors = TREND_COLORS.get(ai_trend, TREND_COLORS["平稳期"])

        indicators_html = ""
        for label, val in [
            ("收盘", f"{ind.get('latest_close', '--')}"),
            ("MA20", f"{ind.get('ma20', '--')}"), ("MA60", f"{ind.get('ma60', '--')}"),
            ("RSI14", f"{ind.get('rsi14', '--')}"), ("ADX", f"{ind.get('adx', '--')}"),
            ("量比", f"{ind.get('vol_ratio', '--')}"),
            ("20日", f"{analysis.get('pct_20d', 0):+.1f}%"),
            ("价格分位", f"{analysis.get('price_position', 0):.0f}%"),
        ]:
            indicators_html += f'<span style="margin-right:12px;font-size:11px;color:#6b7280;">{label}: <b>{val}</b></span>'

        signals_html = ""
        for sig in analysis.get("signals", [])[:6]:
            signals_html += f'<span style="display:inline-block;background:#f3f4f6;padding:2px 8px;border-radius:6px;font-size:11px;margin:2px 4px 2px 0;color:#374151;">{sig}</span>'

        stock_cards += f"""
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;margin-bottom:14px;border-left:4px solid {colors['text']};">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
                <div>
                    <span style="font-size:17px;font-weight:700;color:#111;">{name}</span>
                    <span style="font-size:12px;color:#9ca3af;margin-left:8px;">{code}</span>
                </div>
                <span style="background:{colors['bg']};color:{colors['text']};padding:4px 14px;border-radius:20px;font-size:13px;font-weight:600;">
                    {colors['icon']} {ai_trend}
                    <span style="font-size:10px;opacity:0.7;">(置信度{machine_conf}%)</span>
                </span>
            </div>
            <div style="margin-bottom:8px;">{indicators_html}</div>
            <div style="margin-bottom:8px;">{signals_html}</div>
            <p style="margin:8px 0 0;color:#374151;font-size:13px;line-height:1.6;">{ai_text if ai_text else '（待 AI 分析）'}</p>
        </div>"""

    market_html = ai_result.get("market_overview", "今日数据已采集。") if ai_result else "（待 AI 分析）"
    fund_html = ai_result.get("fund_flow", "") if ai_result else ""
    global_html = ai_result.get("global_view", "") if ai_result else ""
    risk_html = ai_result.get("risk_warning", "股市有风险，投资需谨慎。") if ai_result else "以上分析仅供参考，不构成投资建议。"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Microsoft YaHei',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

<tr><td style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:24px 28px;text-align:center;">
    <h1 style="color:#fff;margin:0;font-size:22px;">📈 A股每日复盘</h1>
    <p style="color:#bfdbfe;margin:6px 0 0;font-size:13px;">{date_str} {weekday} · 长白山 / 协鑫能科 / 西部材料 / 汉缆股份</p>
</td></tr>

<tr><td style="padding:20px 28px 12px;">
    <h2 style="font-size:16px;color:#1e3a5f;margin:0 0 10px;border-bottom:2px solid #2563eb;padding-bottom:6px;">📊 大盘概况</h2>
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0;">{market_html}</p>
</td></tr>

<tr><td style="padding:8px 28px;">
    <h2 style="font-size:16px;color:#1e3a5f;margin:0 0 10px;border-bottom:2px solid #2563eb;padding-bottom:6px;">💰 资金风向</h2>
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0;">{fund_html}</p>
</td></tr>

<tr><td style="padding:8px 28px;">
    <h2 style="font-size:16px;color:#1e3a5f;margin:0 0 10px;border-bottom:2px solid #2563eb;padding-bottom:6px;">🌍 全球视角</h2>
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0;">{global_html}</p>
</td></tr>

<tr><td style="padding:20px 28px 8px;">
    <h2 style="font-size:16px;color:#1e3a5f;margin:0 0 12px;border-bottom:2px solid #2563eb;padding-bottom:6px;">🎯 个股趋势分析</h2>
    {stock_cards}
</td></tr>

<tr><td style="padding:12px 28px 20px;">
    <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:12px 16px;font-size:13px;color:#92400e;">
        ⚠️ <b>风险提示：</b>{risk_html}
    </div>
</td></tr>

<tr><td style="padding:14px 28px;text-align:center;background:#f9fafb;color:#9ca3af;font-size:11px;">
    📬 每个交易日 15:30 推送 · GitHub Actions + AkShare + DeepSeek<br>
    <span style="font-size:10px;">本报告由AI生成，仅供参考，不构成投资建议。</span>
</td></tr>
</table></body></html>"""


# ╔══════════════════════════════════════════════════════╗
# ║  主流程                                            ║
# ╚══════════════════════════════════════════════════════╝

def main():
    log.info("=" * 55)
    log.info("📈 A股每日复盘推送 v2.0")
    log.info("=" * 55)

    # 1. 数据采集
    log.info("\n📡 阶段 1/4: 数据采集")
    index_data, market_stats, sector_flow, global_ctx, stock_data = collect_all_data()

    # 2. 技术分析
    log.info("\n📐 阶段 2/4: 技术分析 & 趋势分类")
    stock_analyses = analyze_all_stocks(stock_data)

    # 3. DeepSeek 分析
    log.info("\n🧠 阶段 3/4: AI 复盘分析")
    ai_result = None
    if DEEPSEEK_API_KEY:
        system, user = build_review_prompt(index_data, market_stats, sector_flow, global_ctx, stock_analyses)
        ai_result = call_deepseek(system, user)

    # 4. 发邮件
    log.info("\n📧 阶段 4/4: 构建邮件 & 发送")
    html = build_review_email(ai_result, stock_analyses)
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"📈 A股每日复盘 — {date_str} | 长白山·协鑫能科·西部材料·汉缆股份"
    send_email(html, subject)

    # 总结
    log.info("\n📊 复盘摘要:")
    for name, a in stock_analyses.items():
        log.info("  %s: %s (置信度%d%%)", name, a["trend"], a["confidence"])
    log.info("=" * 55)


if __name__ == "__main__":
    main()
