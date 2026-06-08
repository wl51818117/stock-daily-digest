#!/usr/bin/env python3
"""
A股分析共享模块 — 配置、数据采集、技术指标、趋势分类
被复盘脚本和预测脚本共同引用。
"""

import os, re, sys, json, smtplib, logging, time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import requests
import numpy as np
import pandas as pd
import akshare as ak

log = logging.getLogger("stock_analyzer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ╔══════════════════════════════════════════════════════╗
# ║  🔧 配置区                                         ║
# ╚══════════════════════════════════════════════════════╝

TRACKED_STOCKS = [
    {"code": "603099", "name": "长白山"},
    {"code": "002015", "name": "协鑫能科"},
    {"code": "002149", "name": "西部材料"},
    {"code": "002498", "name": "汉缆股份"},
]

LOOKBACK_DAYS = 120
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

EMAIL = {k: os.getenv(k, "") for k in [
    "EMAIL_SMTP_SERVER", "EMAIL_SMTP_PORT", "EMAIL_USER",
    "EMAIL_PASSWORD", "EMAIL_TO", "EMAIL_FROM"
]}
EMAIL["SMTP_PORT"] = int(EMAIL.get("EMAIL_SMTP_PORT") or "587")

TREND_COLORS = {
    "上升期":   {"bg": "#fef2f2", "text": "#dc2626", "icon": "🔴"},
    "平稳期":   {"bg": "#f3f4f6", "text": "#6b7280", "icon": "⚪"},
    "高位震荡期": {"bg": "#fff7ed", "text": "#ea580c", "icon": "🟠"},
    "回调期":   {"bg": "#eff6ff", "text": "#2563eb", "icon": "🔵"},
    "底部":     {"bg": "#f0fdf4", "text": "#16a34a", "icon": "🟢"},
}

# 列名映射（中→英），处理不同数据源的列名差异
COLUMN_MAP = {
    "日期": "date", "时间": "date", "股票代码": "code",
    "开盘": "open", "最高": "high", "最低": "low", "收盘": "close",
    "成交量": "volume", "成交额": "amount", "成交量(手)": "volume",
    "换手率": "turnover", "涨跌幅": "change_pct", "涨跌额": "change",
    "流通市值": "market_cap", "振幅": "amplitude",
}


# ╔══════════════════════════════════════════════════════╗
# ║  数据采集模块                                      ║
# ╚══════════════════════════════════════════════════════╝

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """统一列名：中文→英文，全小写"""
    df.columns = [c.lower() for c in df.columns]
    df.columns = [COLUMN_MAP.get(c, c) for c in df.columns]
    return df


def _to_sina_code(code: str) -> str:
    """股票代码转 Sina 格式"""
    if code.startswith("sh") or code.startswith("sz"):
        return code
    if code.startswith(("6", "9")):
        return "sh" + code
    return "sz" + code


def _row_to_dict(row) -> dict:
    """DataFrame row → dict"""
    d = {}
    for k, v in row.items():
        try:
            if isinstance(v, (np.integer,)):
                d[k] = int(v)
            elif isinstance(v, (np.floating,)):
                d[k] = round(float(v), 3)
            elif isinstance(v, (np.bool_,)):
                d[k] = bool(v)
            else:
                d[k] = str(v)
        except Exception:
            d[k] = str(v)
    return d


def fetch_index_data() -> dict:
    """获取主要指数近期行情"""
    log.info("获取指数数据...")
    indices = {
        "上证指数": "sh000001", "深证成指": "sz399001",
        "创业板指": "sz399006", "科创50": "sh000688",
    }
    result = {}
    for name, symbol in indices.items():
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is not None and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                df = df.tail(LOOKBACK_DAYS)
                close_col = "close" if "close" in df.columns else df.columns[-1]
                latest_close = float(df[close_col].iloc[-1]) if len(df) > 0 else 0
                prev_close = float(df[close_col].iloc[-2]) if len(df) > 1 else latest_close
                chg_pct = (latest_close - prev_close) / prev_close * 100 if prev_close else 0
                result[name] = {
                    "latest": _row_to_dict(df.iloc[-1]) if len(df) > 0 else {},
                    "data": df,
                    "change_pct": round(chg_pct, 2),
                    "latest_close": round(latest_close, 2),
                }
                log.info("  %s: %.2f (%.2f%%)", name, latest_close, chg_pct)
            time.sleep(0.3)
        except Exception as e:
            log.warning("  %s 获取失败: %s", name, str(e)[:60])
    return result


def fetch_market_stats() -> dict:
    """获取全市场涨跌统计和成交额"""
    log.info("获取市场统计...")
    result = {"up_count": 0, "down_count": 0, "flat_count": 0,
              "total_amount": 0, "total_amount_yi": 0}
    try:
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            if "涨跌幅" in df.columns:
                chg = pd.to_numeric(df["涨跌幅"], errors="coerce")
                result["up_count"] = int((chg > 0).sum())
                result["down_count"] = int((chg < 0).sum())
                result["flat_count"] = int((chg == 0).sum())
            if "成交额" in df.columns:
                total = pd.to_numeric(df["成交额"], errors="coerce").sum()
                result["total_amount"] = int(total)
                result["total_amount_yi"] = round(total / 1e8, 2)
            log.info("  涨:%d 跌:%d 成交额:%.0f亿",
                     result["up_count"], result["down_count"], result["total_amount_yi"])
        time.sleep(0.5)
    except Exception as e:
        log.warning("  市场统计获取失败: %s", str(e)[:60])
    return result


def fetch_sector_flow() -> list[dict]:
    """获取行业板块资金流向"""
    log.info("获取板块资金流向...")
    sectors = []
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流向")
        if df is not None and not df.empty:
            for _, row in df.head(10).iterrows():
                sectors.append({
                    "name": str(row.get("名称", "")),
                    "net_flow": str(row.get("主力净流入-净额", "")),
                    "net_flow_rate": str(row.get("主力净流入-净占比", "")),
                    "change_pct": str(row.get("涨跌幅", "")),
                })
            log.info("  获取 %d 个行业板块", len(sectors))
        time.sleep(0.5)
    except Exception as e:
        log.warning("  板块资金获取失败: %s", str(e)[:80])
    return sectors


def fetch_stock_history(code: str) -> pd.DataFrame:
    """获取单只股票历史日线数据（多数据源自动切换）"""
    sd = (datetime.now() - timedelta(days=LOOKBACK_DAYS + 30)).strftime("%Y%m%d")
    ed = datetime.now().strftime("%Y%m%d")

    # 数据源 1：东方财富
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                start_date=sd, end_date=ed, adjust="qfq")
        if df is not None and not df.empty and len(df) > 30:
            return _normalize_columns(df)
    except Exception:
        pass

    # 数据源 2：新浪
    try:
        sina_code = _to_sina_code(code)
        df = ak.stock_zh_a_daily(symbol=sina_code, start_date=sd, end_date=ed, adjust="qfq")
        if df is not None and not df.empty and len(df) > 30:
            return _normalize_columns(df)
    except Exception:
        pass

    # 数据源 3：腾讯
    try:
        sina_code = _to_sina_code(code)
        df = ak.stock_zh_a_hist_tx(symbol=sina_code, start_date=sd, end_date=ed)
        if df is not None and not df.empty and len(df) > 30:
            df = _normalize_columns(df)
            if "volume" not in df.columns:
                df["volume"] = 0
            return df
    except Exception:
        pass

    log.warning("  %s 所有数据源均失败", code)
    return pd.DataFrame()


def fetch_global_context() -> dict:
    """获取全球经济背景数据"""
    log.info("获取全球经济数据...")
    result = {
        "sp500": None, "nasdaq": None, "dow_jones": None,
        "vix": None, "gold": None, "oil": None, "usd_cny": None,
    }

    # 美股指数
    for label, sym in [("sp500", "标普500"), ("nasdaq", "纳斯达克"), ("dow_jones", "道琼斯")]:
        try:
            df = ak.index_global_hist_em(symbol=sym)
            if df is not None and not df.empty:
                cols = [c.lower() for c in df.columns]
                close_col = [c for c in cols if "close" in c or "收盘" in c]
                if close_col:
                    latest = float(df.iloc[-1][close_col[0]])
                    prev = float(df.iloc[-2][close_col[0]]) if len(df) > 1 else latest
                    chg = (latest - prev) / prev * 100 if prev else 0
                    result[label] = {"close": round(latest, 2), "change_pct": round(chg, 2)}
            time.sleep(0.3)
        except Exception:
            pass

    # VIX
    try:
        df = ak.index_global_hist_em(symbol="VIX")
        if df is not None and not df.empty:
            cols = [c.lower() for c in df.columns]
            close_col = [c for c in cols if "close" in c or "收盘" in c]
            if close_col:
                result["vix"] = float(df.iloc[-1][close_col[0]])
                log.info("  VIX: %.2f", result["vix"])
        time.sleep(0.3)
    except Exception:
        pass

    # 黄金/原油
    for label, sym in [("gold", "GC00Y"), ("oil", "CL00Y")]:
        try:
            df = ak.futures_foreign_hist(symbol=sym)
            if df is not None and not df.empty:
                cols = [c.lower() for c in df.columns]
                close_col = [c for c in cols if "close" in c or "收盘" in c]
                if close_col:
                    result[label] = float(df.iloc[-1][close_col[0]])
            time.sleep(0.3)
        except Exception:
            pass

    # 美元人民币汇率
    try:
        df = ak.currency_boc_sina(symbol="美元")
        if df is not None and not df.empty:
            rate_col = [c for c in df.columns if "现汇买入" in c or "price" in c.lower()]
            if not rate_col:
                rate_col = [df.columns[-2]]
            result["usd_cny"] = float(df.iloc[-1][rate_col[0]]) / 100
            log.info("  USD/CNY: %.4f", result["usd_cny"])
        time.sleep(0.3)
    except Exception:
        pass

    return result


# ╔══════════════════════════════════════════════════════╗
# ║  技术指标计算                                      ║
# ╚══════════════════════════════════════════════════════╝

def calc_ma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period).mean()


def calc_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    dif = ema_fast - ema_slow
    dea = calc_ema(dif, signal)
    macd_bar = 2 * (dif - dea)
    return dif, dea, macd_bar


def calc_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3):
    low_n = df["low"].rolling(window=n).min()
    high_n = df["high"].rolling(window=n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n) * 100
    k = rsv.ewm(com=m1 - 1, adjust=False).mean()
    d = k.ewm(com=m2 - 1, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_bollinger(close: pd.Series, period: int = 20, std: int = 2):
    mid = calc_ma(close, period)
    std_dev = close.rolling(window=period).std()
    upper = mid + std * std_dev
    lower = mid - std * std_dev
    bandwidth = (upper - lower) / mid * 100
    return upper, mid, lower, bandwidth


def calc_adx(df: pd.DataFrame, period: int = 14):
    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm = pd.Series(0.0, index=df.index)
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx, plus_di, minus_di


def calc_volume_ma(volume: pd.Series, period: int = 20) -> pd.Series:
    return volume.rolling(window=period).mean()


def detect_macd_divergence(close: pd.Series, dif: pd.Series, lookback: int = 60) -> str:
    """检测 MACD 背离"""
    recent_close = close.tail(lookback)
    recent_dif = dif.tail(lookback)
    if len(recent_close) < 30:
        return ""
    half = lookback // 2
    first_close_low = recent_close.iloc[:half].min()
    second_close_low = recent_close.iloc[half:].min()
    first_dif_low = recent_dif.iloc[:half].min()
    second_dif_low = recent_dif.iloc[half:].min()
    first_close_high = recent_close.iloc[:half].max()
    second_close_high = recent_close.iloc[half:].max()
    first_dif_high = recent_dif.iloc[:half].max()
    second_dif_high = recent_dif.iloc[half:].max()

    if second_close_low < first_close_low * 0.98 and second_dif_low > first_dif_low:
        return "[底背离] 价格创近期新低但MACD未跟随，可能筑底"
    if second_close_high > first_close_high * 1.02 and second_dif_high < first_dif_high:
        return "[顶背离] 价格创近期新高但MACD未跟随，注意回落风险"
    return ""


# ╔══════════════════════════════════════════════════════╗
# ║  趋势分类                                          ║
# ╚══════════════════════════════════════════════════════╝

def classify_trend(df: pd.DataFrame) -> dict:
    """综合 6 维度对个股趋势分类"""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    latest_close = float(close.iloc[-1])

    ma5 = calc_ma(close, 5)
    ma10 = calc_ma(close, 10)
    ma20 = calc_ma(close, 20)
    ma60 = calc_ma(close, 60)
    ma120 = calc_ma(close, 120)
    ma250 = calc_ma(close, 250)

    dif, dea, macd_bar = calc_macd(close)
    adx, plus_di, minus_di = calc_adx(df)

    high_120 = high.tail(120).max()
    low_120 = low.tail(120).min()
    range_120 = high_120 - low_120
    price_position = (latest_close - low_120) / range_120 * 100 if range_120 > 0 else 50

    rsi6 = calc_rsi(close, 6)
    rsi14 = calc_rsi(close, 14)
    bb_upper, bb_mid, bb_lower, bb_width = calc_bollinger(close)

    vol_ma20 = calc_volume_ma(volume, 20)
    vol_ratio = float(volume.iloc[-1] / vol_ma20.iloc[-1]) if vol_ma20.iloc[-1] > 0 else 1

    divergence = detect_macd_divergence(close, dif)

    def latest(s):
        return float(s.iloc[-1]) if not pd.isna(s.iloc[-1]) else 0

    m5, m10, m20, m60, m120, m250 = latest(ma5), latest(ma10), latest(ma20), latest(ma60), latest(ma120), latest(ma250)
    d, e, bar = latest(dif), latest(dea), latest(macd_bar)
    a = latest(adx)
    pd_val, md_val = latest(plus_di), latest(minus_di)
    r6, r14 = latest(rsi6), latest(rsi14)
    bb_u, bb_l, bb_w = latest(bb_upper), latest(bb_lower), latest(bb_width)

    # 信号收集
    signals = []

    if latest_close > m20:
        signals.append("价格在MA20上方")
    else:
        signals.append("价格在MA20下方")

    if m5 > m10 > m20:
        signals.append("均线多头排列(MA5>MA10>MA20)")
    elif m5 < m10 < m20:
        signals.append("均线空头排列(MA5<MA10<MA20)")
    else:
        signals.append("均线交织")

    if price_position > 80:
        signals.append(f"价格处于120日高位({price_position:.0f}%分位)")
    elif price_position < 20:
        signals.append(f"价格处于120日低位({price_position:.0f}%分位)")
    else:
        signals.append(f"价格处于120日中位({price_position:.0f}%分位)")

    if d > 0:
        signals.append("DIF在零轴上方")
    else:
        signals.append("DIF在零轴下方")
    if d > e:
        signals.append("MACD金叉状态(DIF>DEA)")
    else:
        signals.append("MACD死叉状态(DIF<DEA)")

    if a < 20:
        signals.append(f"ADX={a:.1f} 无明显趋势")
    elif a < 40:
        signals.append(f"ADX={a:.1f} 趋势形成中")
    else:
        signals.append(f"ADX={a:.1f} 强趋势")

    if r14 > 70:
        signals.append(f"RSI(14)={r14:.0f} 超买区域")
    elif r14 < 30:
        signals.append(f"RSI(14)={r14:.0f} 超卖区域")
    else:
        signals.append(f"RSI(14)={r14:.0f} 正常区域")

    if vol_ratio > 1.5:
        signals.append(f"放量({vol_ratio:.1f}倍均量)")
    elif vol_ratio < 0.5:
        signals.append(f"缩量({vol_ratio:.1f}倍均量)")

    if latest_close >= bb_u * 0.98:
        signals.append("价格触及布林上轨")
    elif latest_close <= bb_l * 1.02:
        signals.append("价格触及布林下轨")

    if bb_w < 5:
        signals.append("布林带收窄(变盘信号)")
    elif bb_w > 15:
        signals.append("布林带宽阔(波动加剧)")

    if divergence:
        signals.append(divergence)

    # 趋势判定
    trend = "平稳期"
    confidence = 50

    close_20d_ago = float(close.iloc[-21]) if len(close) > 20 else float(close.iloc[0])
    pct_20d = (latest_close - close_20d_ago) / close_20d_ago * 100

    recent_high_60 = high.tail(60).max()
    drawdown_from_high = (latest_close - recent_high_60) / recent_high_60 * 100

    is_bottom_like = (
        price_position < 25 and r14 < 35 and vol_ratio < 0.8
        and (d > e or "底背离" in divergence)
    )
    if is_bottom_like and price_position < 15:
        trend, confidence = "底部", 75
    elif is_bottom_like:
        trend, confidence = "底部", 60

    is_uptrend = (
        latest_close > m20 and m5 > m10 > m20 and d > e
        and a > 20 and pd_val > md_val and 30 < price_position < 80
    )
    if is_uptrend and a > 30:
        trend, confidence = "上升期", 80
    elif is_uptrend:
        trend, confidence = "上升期", 65

    is_high_consolidation = (
        price_position > 75 and r14 > 55 and a < 25
        and (d < e or (d > 0 and bar < 0))
    )
    if is_high_consolidation and price_position > 85:
        trend, confidence = "高位震荡期", 80
    elif is_high_consolidation:
        trend, confidence = "高位震荡期", 65

    is_pullback = (
        drawdown_from_high < -8 and d < e and m5 < m10
        and latest_close > m60
    )
    if is_pullback and drawdown_from_high < -15:
        trend, confidence = "回调期", 80
    elif is_pullback:
        trend, confidence = "回调期", 65

    if trend not in ("上升期", "底部", "高位震荡期", "回调期") or (
        a < 20 and abs(pct_20d) < 5 and not is_bottom_like
    ):
        trend = "平稳期"
        confidence = max(confidence, 55)

    key_levels = {
        "resistance": round(float(high.tail(60).max()), 2),
        "support": round(float(low.tail(60).min()), 2),
        "ma20": round(m20, 2), "ma60": round(m60, 2),
        "ma120": round(m120, 2),
        "ma250": round(m250, 2) if not pd.isna(m250) else None,
    }

    return {
        "trend": trend,
        "confidence": confidence,
        "price_position": round(price_position, 1),
        "pct_20d": round(pct_20d, 2),
        "drawdown_from_high": round(drawdown_from_high, 2),
        "key_levels": key_levels,
        "indicators": {
            "ma5": round(m5, 2), "ma10": round(m10, 2), "ma20": round(m20, 2),
            "ma60": round(m60, 2), "ma120": round(m120, 2),
            "dif": round(d, 3), "dea": round(e, 3), "macd_bar": round(bar, 3),
            "adx": round(a, 1), "plus_di": round(pd_val, 1), "minus_di": round(md_val, 1),
            "rsi6": round(r6, 1), "rsi14": round(r14, 1),
            "bb_upper": round(bb_u, 2), "bb_lower": round(bb_l, 2), "bb_width": round(bb_w, 1),
            "vol_ratio": round(vol_ratio, 2),
            "latest_close": round(latest_close, 2),
        },
        "signals": signals,
    }


# ╔══════════════════════════════════════════════════════╗
# ║  共享工具（DeepSeek 调用 + 邮件发送）              ║
# ╚══════════════════════════════════════════════════════╝

def call_deepseek(system: str, user: str) -> Optional[dict]:
    """调用 DeepSeek API"""
    if not DEEPSEEK_API_KEY:
        log.warning("未配置 DEEPSEEK_API_KEY，跳过 AI 分析")
        return None

    log.info("调用 DeepSeek...")
    try:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 2500,
                "temperature": 0.6,
            },
            timeout=90,
        )
        data = resp.json()
        usage = data.get("usage", {})
        cost = (usage.get("prompt_tokens", 0) * 0.00014 +
                usage.get("completion_tokens", 0) * 0.00028) / 1000
        log.info("DeepSeek | 输入:%s 输出:%s tokens | $%.5f",
                 usage.get("prompt_tokens", "?"),
                 usage.get("completion_tokens", "?"), cost)

        content = data["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            log.warning("DeepSeek 返回无法解析 JSON")
            return None
    except Exception as e:
        log.error("DeepSeek 调用失败: %s", str(e)[:100])
        return None


def send_email(html: str, subject: str):
    """发送邮件"""
    required = ["EMAIL_SMTP_SERVER", "EMAIL_USER", "EMAIL_PASSWORD", "EMAIL_TO", "EMAIL_FROM"]
    missing = [k for k in required if not EMAIL.get(k)]
    if missing:
        log.warning("邮件配置不完整，缺少: %s。跳过发送。", ", ".join(missing))
        log.info("HTML 已生成，可手动查看")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL["EMAIL_FROM"]
    msg["To"] = EMAIL["EMAIL_TO"]
    msg.attach(MIMEText(subject + "\n\n请查看 HTML 邮件。", "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    port = int(EMAIL["EMAIL_SMTP_PORT"])
    s = smtplib.SMTP_SSL(EMAIL["EMAIL_SMTP_SERVER"], port, timeout=30) if port == 465 else smtplib.SMTP(EMAIL["EMAIL_SMTP_SERVER"], port, timeout=30)
    if port != 465:
        s.starttls()
    s.login(EMAIL["EMAIL_USER"], EMAIL["EMAIL_PASSWORD"])
    s.sendmail(EMAIL["EMAIL_FROM"], EMAIL["EMAIL_TO"], msg.as_string())
    s.quit()
    log.info("邮件已发送 → %s", EMAIL["EMAIL_TO"])


def collect_all_data() -> tuple:
    """完整数据采集流程，返回 (index_data, market_stats, sector_flow, global_ctx, stock_data)"""
    index_data = fetch_index_data()
    market_stats = fetch_market_stats()
    sector_flow = fetch_sector_flow()
    global_ctx = fetch_global_context()

    stock_data = {}
    for s in TRACKED_STOCKS:
        log.info("  获取 %s(%s)...", s["name"], s["code"])
        df = fetch_stock_history(s["code"])
        if df is not None and not df.empty and len(df) > 30:
            stock_data[s["name"]] = df
            log.info("    获取 %d 条数据", len(df))
        else:
            log.warning("    %s 数据不足", s["name"])
        time.sleep(0.5)
    return index_data, market_stats, sector_flow, global_ctx, stock_data


def analyze_all_stocks(stock_data: dict) -> dict:
    """对所有股票执行技术分析和趋势分类"""
    stock_analyses = {}
    for name, df in stock_data.items():
        analysis = classify_trend(df)
        stock_analyses[name] = analysis
        log.info("  %s → %s (置信度 %d%%, 价格分位 %.0f%%)",
                 name, analysis["trend"], analysis["confidence"],
                 analysis["price_position"])
    return stock_analyses


def build_stocks_brief(stock_analyses: dict) -> dict:
    """构建个股数据摘要（发给 AI）"""
    stocks_brief = {}
    for name, analysis in stock_analyses.items():
        ind = analysis.get("indicators", {})
        stocks_brief[name] = {
            "code": [s["code"] for s in TRACKED_STOCKS if s["name"] == name][0],
            "latest_close": ind.get("latest_close", 0),
            "trend": analysis.get("trend", ""),
            "confidence": analysis.get("confidence", 0),
            "price_position": analysis.get("price_position", 0),
            "pct_20d": analysis.get("pct_20d", 0),
            "drawdown": analysis.get("drawdown_from_high", 0),
            "indicators": {
                "ma5": ind.get("ma5", 0), "ma20": ind.get("ma20", 0),
                "ma60": ind.get("ma60", 0), "ma120": ind.get("ma120", 0),
                "rsi14": ind.get("rsi14", 0), "adx": ind.get("adx", 0),
                "macd_dif": ind.get("dif", 0), "macd_dea": ind.get("dea", 0),
                "vol_ratio": ind.get("vol_ratio", 1),
            },
            "signals": analysis.get("signals", []),
        }
    return stocks_brief
