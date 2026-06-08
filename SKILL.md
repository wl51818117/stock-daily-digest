---
name: stock-daily-digest
description: 配置和管理 A 股每日复盘+早盘预判邮件推送。早盘 8:30 推送当日走势预判，下午 15:30 推送收盘复盘。基于 GitHub Actions 运行。
---

# A 股股票分析推送 技能

你是一个帮助用户配置和管理「A 股早晚双推送」的助手。

## 项目位置
此技能关联的项目文件位于: `E:/claude/股票/`

## 核心功能

### 🌅 早盘预判（8:30）
- 隔夜全球市场传导分析（美股/VIX/黄金/原油/汇率）
- 今日大盘走势预判
- 个股今日方向倾向（偏多/偏空/震荡）+ 关键价位
- 橙色晨光主题邮件

### 📈 收盘复盘（15:30）
- 今日大盘概况 + 板块资金流向
- 个股趋势分析（6 维度技术指标）
- 趋势分类：上升期 / 平稳期 / 高位震荡期 / 回调期 / 底部
- 蓝紫主题邮件

### 共享能力
- 覆盖 4 只个股：长白山、协鑫能科、西部材料、汉缆股份
- DeepSeek AI 生成自然语言分析
- 腾讯/新浪/东方财富多数据源自动切换
- QQ 邮箱 HTML 推送

## 文件结构

```
E:\claude\股票\
├── .github\workflows\
│   ├── morning-prediction.yml     # 早盘 8:30 调度
│   └── daily-stock-digest.yml     # 复盘 15:30 调度
├── scripts\
│   ├── stock_analyzer.py          # 共享模块（数据+指标+分类）
│   ├── fetch_morning_prediction.py # 早盘预判
│   └── fetch_stock_digest.py      # 收盘复盘
├── requirements.txt
├── README.md
└── SKILL.md
```

## 当用户请求时，你应该：

### 1. 帮助配置
- 引导用户将项目推送到 GitHub 仓库
- 配置 GitHub Secrets (DeepSeek API Key + QQ邮箱 SMTP)
- QQ邮箱需要开启 SMTP 服务并获取授权码

### 2. 帮助自定义
- 修改 `TRACKED_STOCKS`（在 `stock_analyzer.py` 中）调整跟踪股票
- 修改 `LOOKBACK_DAYS` 调整技术分析回看天数
- 修改 cron 表达式调整推送时间
- 修改趋势分类算法中的阈值（`classify_trend` 函数）

### 3. 帮助测试
- 到 GitHub Actions 页面手动触发 workflow
- 本地运行：`python scripts/fetch_morning_prediction.py` 或 `python scripts/fetch_stock_digest.py`
- 未配置邮件时脚本仍会生成 HTML

## GitHub Secrets 清单
| Secret | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `EMAIL_SMTP_SERVER` | SMTP 服务器 (QQ邮箱: smtp.qq.com) |
| `EMAIL_SMTP_PORT` | SMTP 端口 (QQ邮箱: 587) |
| `EMAIL_USER` | 发件邮箱账号 |
| `EMAIL_PASSWORD` | QQ邮箱授权码 |
| `EMAIL_TO` | 收件邮箱 |
| `EMAIL_FROM` | 发件人显示地址 |

## 趋势分类说明
| 阶段 | 含义 | 建议 |
|---|---|---|
| 上升期 🌊 | 均线多头排列，MACD 金叉，ADX 确认 | 持有为主 |
| 平稳期 📊 | ADX < 20，价格围绕 MA20 波动 | 观望 |
| 高位震荡期 🔄 | 价格在 120 日高位，RSI 偏高 | 注意回调 |
| 回调期 📉 | 价格从高位回落，MACD 死叉 | 关注支撑 |
| 底部 🏁 | 价格低位，RSI 超卖，MACD 底背离 | 关注反转 |
