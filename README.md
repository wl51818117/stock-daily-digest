# 📈 A股早晚双推送

- 🌅 **早盘 8:30**：今日预判（隔夜全球传导 + 大盘预判 + 个股方向 + 关键价位）
- 📈 **下午 15:30**：收盘复盘（大盘概况 + 资金流向 + 个股趋势分析）

覆盖：长白山(603099) · 协鑫能科(002015) · 西部材料(002149) · 汉缆股份(002498)

## 🎯 功能

### 早盘预判（8:30）
- 隔夜美股/VIX/黄金/原油/汇率综合传导分析
- 今日大盘可能运行区间
- 个股今日方向倾向（偏多/偏空/震荡）+ 压力位/支撑位
- 晨光橙黄色调邮件

### 收盘复盘（15:30）
- 上证/深证/创业板/科创50 指数表现 + 涨跌统计
- 行业板块资金净流入排名
- 4只个股 6 维度技术分析 + 趋势分类
- 蓝紫色调邮件

### 趋势阶段分类
| 上升期 | 平稳期 | 高位震荡期 | 回调期 | 底部 |
|---|---|---|---|---|
| 🌊 持有 | 📊 观望 | 🔄 注意风险 | 📉 关注支撑 | 🏁 关注反转 |

## 🚀 快速开始

### 1. 推送至 GitHub

```bash
cd E:\claude\股票
git init
git add .
git commit -m "init: A股早晚双推送"
git remote add origin <你的仓库地址>
git push -u origin main
```

### 2. 配置 GitHub Secrets

Settings → Secrets and variables → Actions：

| Secret | 值 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `EMAIL_SMTP_SERVER` | smtp.qq.com |
| `EMAIL_SMTP_PORT` | 587 |
| `EMAIL_USER` | QQ 邮箱账号 |
| `EMAIL_PASSWORD` | QQ 邮箱授权码 |
| `EMAIL_TO` | 接收报告的邮箱 |
| `EMAIL_FROM` | 发件人显示地址 |

### 3. 手动测试

Actions → Morning Stock Prediction / Daily Stock Digest → Run workflow

## 📋 本地运行

```bash
pip install -r requirements.txt

# 早盘预判
DEEPSEEK_API_KEY=sk-xxx python scripts/fetch_morning_prediction.py

# 收盘复盘
DEEPSEEK_API_KEY=sk-xxx python scripts/fetch_stock_digest.py
```

## 🏗 项目结构

```
├── .github/workflows/
│   ├── morning-prediction.yml      # 8:30 触发器
│   └── daily-stock-digest.yml      # 15:30 触发器
├── scripts/
│   ├── stock_analyzer.py           # 共享模块
│   ├── fetch_morning_prediction.py # 早盘预判
│   └── fetch_stock_digest.py       # 收盘复盘
├── requirements.txt
└── README.md
```

## ⚠️ 免责声明

本报告由 AI 自动生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。
