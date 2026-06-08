#!/usr/bin/env python3
"""
A股早盘预测推送 — 上午 8:30 发送
隔夜全球传导 + 今日预判 + 潜力推荐 + 小白建议
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

BIAS_COLORS = {
    "偏多": {"bg": "#fef2f2", "text": "#dc2626", "icon": "📈"},
    "偏空": {"bg": "#eff6ff", "text": "#2563eb", "icon": "📉"},
    "震荡": {"bg": "#f3f4f6", "text": "#6b7280", "icon": "📊"},
}


# ╔══════════════════════════════════════════════════════╗
# ║  预测 Prompt                                       ║
# ╚══════════════════════════════════════════════════════╝

def build_prediction_prompt(index_data, market_stats, sector_flow, global_ctx,
                            stock_analyses, potential_stocks):
    indices_brief = {}
    for name, info in index_data.items():
        indices_brief[name] = {
            "latest": info.get("latest_close", info.get("latest", {}).get("close", "N/A")),
            "change_pct": info.get("change_pct", 0),
        }

    stocks_brief = build_stocks_brief(stock_analyses)

    potential_brief = []
    for p in potential_stocks[:5]:
        potential_brief.append({
            "name": p["name"], "code": p["code"],
            "score": p["potential_score"], "trend": p["trend"],
            "price_position": p["price_position"],
            "reasons": p["potential_reasons"][:3],
        })

    payload = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "type": "早盘预判",
        "indices": indices_brief,
        "global_overnight": {
            "sp500": global_ctx.get("sp500"), "nasdaq": global_ctx.get("nasdaq"),
            "dow_jones": global_ctx.get("dow_jones"), "vix": global_ctx.get("vix"),
            "gold": global_ctx.get("gold"), "oil": global_ctx.get("oil"),
            "usd_cny": global_ctx.get("usd_cny"),
        },
        "tracked_stocks": stocks_brief,
        "potential_candidates": potential_brief,
    }

    system = """你是资深A股策略分析师。请用通俗易懂的语言做盘前预判。

要求：
1. **隔夜传导**：美股/VIX/黄金/原油对A股开盘的影响（2-3句话，说清楚多空方向）
2. **大盘预判**：今日上证可能怎么走（1-2句话，用普通话说）
3. **个股预判**：每只2-3句话，包含：
   - 今日方向倾向和理由、关键价位
   - 「小白建议」：最直白的话说今天该干嘛
   - 「做T建议」：判断今天是否适合做T。适合给买卖价位，不适合说原因
4. **潜力推荐**：从候选池选1-2只，说明为什么今天值得关注。用小白能听懂的话解释逻辑。
5. **风险备忘**：今天最该警惕的1件事

只返回 JSON：
{
  "overnight_impact": "...",
  "market_outlook": "...",
  "stocks": [
    {"name": "长白山", "bias": "偏多", "analysis": "...", "resistance": "40", "support": "35", "beginner_advice": "...", "daytrade": "适合，回踩35低吸，反弹40高抛"}
  ],
  "pick": {"name": "XXX", "code": "000001", "reason": "..."},
  "risk_memo": "..."
}"""

    user = f"盘前数据：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    return system, user


# ╔══════════════════════════════════════════════════════╗
# ║  预测邮件模板                                      ║
# ╚══════════════════════════════════════════════════════╝

def build_prediction_email(ai_result, stock_analyses):
    date_str = datetime.now().strftime("%Y年%m月%d日")
    weekday = ["周一","周二","周三","周四","周五","周六","周日"][datetime.now().weekday()]

    overnight_html = ai_result.get("overnight_impact", "数据已采集") if ai_result else "（待 AI 分析）"
    market_outlook_html = ai_result.get("market_outlook", "") if ai_result else ""

    # ── 个股预判卡片 ──
    stock_cards = ""
    for s in TRACKED_STOCKS:
        name, code = s["name"], s["code"]
        analysis = stock_analyses.get(name, {})
        ind = analysis.get("indicators", {})
        machine_trend = analysis.get("trend", "平稳期")

        ai_bias, ai_text, ai_advice, ai_daytrade, ai_res, ai_sup = "震荡", "", "", "", "", ""
        if ai_result:
            for ai_s in ai_result.get("stocks", []):
                if ai_s.get("name") == name:
                    ai_bias = ai_s.get("bias", "震荡")
                    ai_text = ai_s.get("analysis", "")
                    ai_advice = ai_s.get("beginner_advice", "")
                    ai_daytrade = ai_s.get("daytrade", "")
                    ai_res = ai_s.get("resistance", "")
                    ai_sup = ai_s.get("support", "")
                    break

        colors = BIAS_COLORS.get(ai_bias, BIAS_COLORS["震荡"])
        trend_colors = TREND_COLORS.get(machine_trend, TREND_COLORS["平稳期"])

        levels_html = ""
        if ai_res:
            levels_html += f'<span style="margin-right:10px;font-size:11px;color:#dc2626;">压力: <b>{ai_res}</b></span>'
        if ai_sup:
            levels_html += f'<span style="margin-right:10px;font-size:11px;color:#16a34a;">支撑: <b>{ai_sup}</b></span>'

        advice_html = ""
        if ai_advice:
            advice_html = f'<div style="margin-top:8px;background:#f0fdf4;border-radius:6px;padding:8px 12px;font-size:13px;color:#166534;"><b>💬 小白建议：</b>{ai_advice}</div>'
        daytrade_html = ""
        if ai_daytrade:
            daytrade_html = f'<div style="margin-top:6px;background:#eff6ff;border-radius:6px;padding:8px 12px;font-size:13px;color:#1e40af;"><b>🔁 做T参考：</b>{ai_daytrade}</div>'

        stock_cards += f"""
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;margin-bottom:14px;border-left:4px solid {colors['text']};">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <div>
                    <span style="font-size:17px;font-weight:700;color:#111;">{name}</span>
                    <span style="background:{trend_colors['bg']};color:{trend_colors['text']};padding:2px 8px;border-radius:10px;font-size:10px;margin-left:8px;">昨日: {machine_trend}</span>
                </div>
                <span style="background:{colors['bg']};color:{colors['text']};padding:4px 14px;border-radius:20px;font-size:13px;font-weight:600;">
                    {colors['icon']} 今日{ai_bias}
                </span>
            </div>
            <div style="margin-bottom:6px;">{levels_html}</div>
            <p style="margin:6px 0 0;color:#374151;font-size:13px;line-height:1.6;">{ai_text if ai_text else '（待 AI 分析）'}</p>
            {advice_html}
            {daytrade_html}
        </div>"""

    # ── 潜力推荐 ──
    pick_html = ""
    if ai_result and ai_result.get("pick"):
        p = ai_result["pick"]
        pick_html = f"""
        <div style="background:linear-gradient(135deg,#fef3c7,#fde68a);border:1px solid #f59e0b;border-radius:10px;padding:16px 20px;margin-bottom:14px;">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                <span style="font-size:20px;">⭐</span>
                <span style="font-size:17px;font-weight:700;color:#92400e;">{p.get('name', '')}</span>
                <span style="font-size:12px;color:#a16207;">{p.get('code', '')}</span>
            </div>
            <p style="margin:0;color:#78350f;font-size:13px;line-height:1.7;">{p.get('reason', '')}</p>
        </div>"""

    risk_html = ai_result.get("risk_memo", "控制仓位，理性交易。") if ai_result else "以上预判仅供参考。"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Microsoft YaHei',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

<tr><td style="background:linear-gradient(135deg,#f97316,#f59e0b);padding:24px 28px;text-align:center;">
    <h1 style="color:#fff;margin:0;font-size:22px;">🌅 A股早盘预判</h1>
    <p style="color:#fef3c7;margin:6px 0 0;font-size:13px;">{date_str} {weekday} · 开盘前参考</p>
</td></tr>

<tr><td style="padding:20px 28px 12px;">
    <h2 style="font-size:16px;color:#c2410c;margin:0 0 10px;border-bottom:2px solid #f97316;padding-bottom:6px;">🌍 隔夜全球传导</h2>
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0;">{overnight_html}</p>
</td></tr>

<tr><td style="padding:8px 28px;">
    <h2 style="font-size:16px;color:#c2410c;margin:0 0 10px;border-bottom:2px solid #f97316;padding-bottom:6px;">📊 今日大盘预判</h2>
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0;">{market_outlook_html}</p>
</td></tr>

<tr><td style="padding:20px 28px 8px;">
    <h2 style="font-size:16px;color:#c2410c;margin:0 0 12px;border-bottom:2px solid #f97316;padding-bottom:6px;">🎯 个股今日预判</h2>
    {stock_cards}
</td></tr>

<tr><td style="padding:8px 28px;">
    <h2 style="font-size:16px;color:#c2410c;margin:0 0 12px;border-bottom:2px solid #f59e0b;padding-bottom:6px;">⭐ 潜力关注</h2>
    {pick_html if pick_html else '<p style="color:#9ca3af;font-size:13px;">（待 AI 分析）</p>'}
</td></tr>

<tr><td style="padding:12px 28px 20px;">
    <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:12px 16px;font-size:13px;color:#92400e;">
        ⚠️ <b>今日风险备忘：</b>{risk_html}
    </div>
</td></tr>

<tr><td style="padding:14px 28px;text-align:center;background:#f9fafb;color:#9ca3af;font-size:11px;">
    📬 交易日 8:30 推送 · AkShare + DeepSeek<br>
    <span style="font-size:10px;">AI生成仅供参考，不构成投资建议。</span>
</td></tr>
</table></body></html>"""


# ╔══════════════════════════════════════════════════════╗
# ║  主流程                                            ║
# ╚══════════════════════════════════════════════════════╝

def main():
    log.info("=" * 55)
    log.info("🌅 A股早盘预判推送 v3.0")

    # 1. 数据采集
    log.info("\n📡 阶段 1/4: 数据采集")
    index_data, market_stats, sector_flow, global_ctx, stock_data, potential_stocks = collect_all_data()

    # 2. 技术分析
    log.info("\n📐 阶段 2/4: 技术分析 & 潜力扫描")
    stock_analyses = analyze_all_stocks(stock_data)

    # 3. DeepSeek
    log.info("\n🧠 阶段 3/4: AI 盘前预判")
    ai_result = None
    if DEEPSEEK_API_KEY:
        system, user = build_prediction_prompt(index_data, market_stats, sector_flow,
                                               global_ctx, stock_analyses, potential_stocks)
        ai_result = call_deepseek(system, user)

    # 4. 邮件
    log.info("\n📧 阶段 4/4: 发送邮件")
    html = build_prediction_email(ai_result, stock_analyses)
    date_str = datetime.now().strftime("%Y-%m-%d")
    send_email(html, f"🌅 A股早盘预判 — {date_str}")

    log.info("\n📊 预判完成")
    for name, a in stock_analyses.items():
        log.info("  %s: %s (%d%%)", name, a["trend"], a["confidence"])
    log.info("=" * 55)


if __name__ == "__main__":
    main()
