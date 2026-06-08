#!/usr/bin/env python3
"""
A股早盘预测推送 — 上午 8:30 发送
基于隔夜全球市场和技术指标，预判当日走势。
"""

import sys, os, json, logging, time
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

from stock_analyzer import (
    log, TRACKED_STOCKS, DEEPSEEK_API_KEY, DEEPSEEK_MODEL, EMAIL, TREND_COLORS,
    collect_all_data, analyze_all_stocks, build_stocks_brief,
    call_deepseek, send_email,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ╔══════════════════════════════════════════════════════╗
# ║  预测 DeepSeek Prompt                              ║
# ╚══════════════════════════════════════════════════════╝

def build_prediction_prompt(index_data, market_stats, sector_flow, global_ctx, stock_analyses):
    """构建预判分析的 DeepSeek 请求"""
    indices_brief = {}
    for name, info in index_data.items():
        indices_brief[name] = {
            "latest": info.get("latest_close", info.get("latest", {}).get("close", "N/A")),
            "change_pct": info.get("change_pct", 0),
        }

    stocks_brief = build_stocks_brief(stock_analyses)

    payload = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "type": "早盘预判（基于昨日收盘数据+隔夜全球市场）",
        "indices": indices_brief,
        "global_overnight": {
            "sp500": global_ctx.get("sp500"),
            "nasdaq": global_ctx.get("nasdaq"),
            "dow_jones": global_ctx.get("dow_jones"),
            "vix": global_ctx.get("vix"),
            "gold": global_ctx.get("gold"),
            "oil": global_ctx.get("oil"),
            "usd_cny": global_ctx.get("usd_cny"),
        },
        "stocks": stocks_brief,
    }

    system = """你是资深A股策略分析师，专长于盘前预判。请结合隔夜全球市场走势和个股技术面，
对今日A股做出前瞻性预判。风格：客观、具体、可操作。

要求：
1. **隔夜传导**（重点）：美股三大指数涨跌、VIX、黄金原油、美元汇率的综合信号，
   判断对A股开盘及全天的可能传导方向（偏多/偏空/中性）。2-3句话。
2. **大盘预判**：今日上证可能运行区间和核心矛盾，1-2句话。
3. **个股预判**：每只股票2-3句话，必须包含：
   - 今日可能的方向倾向（偏多/偏空/震荡）及理由
   - 关键价位：上方压力位、下方支撑位
   - 一个具体的情景推演（如果突破X则看Y，如果跌破A则看B）
4. **风险备忘**：今天最该警惕的一件事（1句话）

趋势参考（昨日收盘状态）：
- 上升期：多头排列，顺势看多但注意节奏
- 平稳期：等待方向选择，不宜激进
- 高位震荡期：高抛低吸思路，注意假突破
- 回调期：关注支撑是否有效，企稳前谨慎
- 底部：关注反转信号，可分批试探但不重仓

只返回 JSON：
{
  "overnight_impact": "...",
  "market_outlook": "...",
  "stocks": [
    {"name": "长白山", "bias": "偏多", "analysis": "...", "resistance": "40.00", "support": "35.00"}
  ],
  "risk_memo": "..."
}"""

    user = f"今日盘前数据：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    return system, user


# ╔══════════════════════════════════════════════════════╗
# ║  预测邮件模板（晨光主题）                          ║
# ╚══════════════════════════════════════════════════════╝

BIAS_COLORS = {
    "偏多":  {"bg": "#fef2f2", "text": "#dc2626", "icon": "📈"},
    "偏空":  {"bg": "#eff6ff", "text": "#2563eb", "icon": "📉"},
    "震荡":  {"bg": "#f3f4f6", "text": "#6b7280", "icon": "📊"},
}


def build_prediction_email(ai_result, stock_analyses):
    """构建预测 HTML 邮件（晨光橙黄主题）"""
    date_str = datetime.now().strftime("%Y年%m月%d日")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]

    # ── 隔夜全球数据卡片 ──
    overnight_html = ai_result.get("overnight_impact", "数据已采集，详见下方。") if ai_result else "（待 AI 分析）"
    market_outlook_html = ai_result.get("market_outlook", "—") if ai_result else "（待 AI 分析）"

    # ── 个股预判卡片 ──
    stock_cards = ""
    for s in TRACKED_STOCKS:
        name, code = s["name"], s["code"]
        analysis = stock_analyses.get(name, {})
        ind = analysis.get("indicators", {})
        machine_trend = analysis.get("trend", "平稳期")

        ai_bias = "震荡"
        ai_text = ""
        ai_resistance = ""
        ai_support = ""
        if ai_result:
            for ai_s in ai_result.get("stocks", []):
                if ai_s.get("name") == name:
                    ai_bias = ai_s.get("bias", "震荡")
                    ai_text = ai_s.get("analysis", "")
                    ai_resistance = ai_s.get("resistance", "")
                    ai_support = ai_s.get("support", "")
                    break

        colors = BIAS_COLORS.get(ai_bias, BIAS_COLORS["震荡"])
        trend_colors = TREND_COLORS.get(machine_trend, TREND_COLORS["平稳期"])

        # 关键价位行
        levels_html = ""
        kls = analysis.get("key_levels", {})
        if ai_resistance:
            levels_html += f'<span style="margin-right:10px;font-size:11px;color:#dc2626;">压力: <b>{ai_resistance}</b></span>'
        if ai_support:
            levels_html += f'<span style="margin-right:10px;font-size:11px;color:#16a34a;">支撑: <b>{ai_support}</b></span>'
        if not levels_html:
            levels_html = f'<span style="margin-right:10px;font-size:11px;color:#6b7280;">60日高: <b>{kls.get("resistance", "--")}</b></span>'
            levels_html += f'<span style="margin-right:10px;font-size:11px;color:#6b7280;">60日低: <b>{kls.get("support", "--")}</b></span>'

        stock_cards += f"""
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;margin-bottom:14px;border-left:4px solid {colors['text']};">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
                <div>
                    <span style="font-size:17px;font-weight:700;color:#111;">{name}</span>
                    <span style="font-size:12px;color:#9ca3af;margin-left:8px;">{code}</span>
                    <span style="background:{trend_colors['bg']};color:{trend_colors['text']};padding:2px 8px;border-radius:10px;font-size:10px;margin-left:8px;">{trend_colors['icon']} {machine_trend}</span>
                </div>
                <span style="background:{colors['bg']};color:{colors['text']};padding:4px 14px;border-radius:20px;font-size:13px;font-weight:600;">
                    {colors['icon']} 今日{ai_bias}
                </span>
            </div>
            <div style="margin-bottom:8px;">{levels_html}</div>
            <p style="margin:8px 0 0;color:#374151;font-size:13px;line-height:1.6;">{ai_text if ai_text else '（待 AI 分析）'}</p>
        </div>"""

    risk_html = ai_result.get("risk_memo", "控制仓位，理性交易。") if ai_result else "以上预判仅供参考，不构成投资建议。"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Microsoft YaHei',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

<!-- 晨光头部 -->
<tr><td style="background:linear-gradient(135deg,#f97316,#f59e0b);padding:24px 28px;text-align:center;">
    <h1 style="color:#fff;margin:0;font-size:22px;">🌅 A股早盘预判</h1>
    <p style="color:#fef3c7;margin:6px 0 0;font-size:13px;">{date_str} {weekday} · 开盘前参考 · 长白山 / 协鑫能科 / 西部材料 / 汉缆股份</p>
</td></tr>

<!-- 隔夜全球 -->
<tr><td style="padding:20px 28px 12px;">
    <h2 style="font-size:16px;color:#c2410c;margin:0 0 10px;border-bottom:2px solid #f97316;padding-bottom:6px;">🌍 隔夜全球传导</h2>
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0;">{overnight_html}</p>
</td></tr>

<!-- 大盘预判 -->
<tr><td style="padding:8px 28px;">
    <h2 style="font-size:16px;color:#c2410c;margin:0 0 10px;border-bottom:2px solid #f97316;padding-bottom:6px;">📊 今日大盘预判</h2>
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0;">{market_outlook_html}</p>
</td></tr>

<!-- 个股预判 -->
<tr><td style="padding:20px 28px 8px;">
    <h2 style="font-size:16px;color:#c2410c;margin:0 0 12px;border-bottom:2px solid #f97316;padding-bottom:6px;">🎯 个股今日预判</h2>
    {stock_cards}
</td></tr>

<!-- 风险备忘 -->
<tr><td style="padding:12px 28px 20px;">
    <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:12px 16px;font-size:13px;color:#92400e;">
        ⚠️ <b>今日风险备忘：</b>{risk_html}
    </div>
</td></tr>

<tr><td style="padding:14px 28px;text-align:center;background:#f9fafb;color:#9ca3af;font-size:11px;">
    📬 每个交易日 8:30 推送 · GitHub Actions + AkShare + DeepSeek<br>
    <span style="font-size:10px;">本报告由AI生成，仅供参考，不构成投资建议。</span>
</td></tr>
</table></body></html>"""


# ╔══════════════════════════════════════════════════════╗
# ║  主流程                                            ║
# ╚══════════════════════════════════════════════════════╝

def main():
    log.info("=" * 55)
    log.info("🌅 A股早盘预判推送 v1.0")
    log.info("=" * 55)

    # 1. 数据采集
    log.info("\n📡 阶段 1/4: 数据采集")
    index_data, market_stats, sector_flow, global_ctx, stock_data = collect_all_data()

    # 2. 技术分析
    log.info("\n📐 阶段 2/4: 技术分析 & 趋势分类")
    stock_analyses = analyze_all_stocks(stock_data)

    # 3. DeepSeek 预判
    log.info("\n🧠 阶段 3/4: AI 盘前预判")
    ai_result = None
    if DEEPSEEK_API_KEY:
        system, user = build_prediction_prompt(index_data, market_stats, sector_flow, global_ctx, stock_analyses)
        ai_result = call_deepseek(system, user)

    # 4. 发邮件
    log.info("\n📧 阶段 4/4: 构建邮件 & 发送")
    html = build_prediction_email(ai_result, stock_analyses)
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"🌅 A股早盘预判 — {date_str} | 长白山·协鑫能科·西部材料·汉缆股份"
    send_email(html, subject)

    # 总结
    log.info("\n📊 预判摘要:")
    if ai_result:
        log.info("  隔夜: %s", ai_result.get("overnight_impact", "")[:80])
    for name, a in stock_analyses.items():
        log.info("  %s: %s (置信度%d%%)", name, a["trend"], a["confidence"])
    log.info("=" * 55)


if __name__ == "__main__":
    main()
