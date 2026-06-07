from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import anthropic
import os
import httpx
from datetime import datetime

app = FastAPI(title="MT5 Claude Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

analyses_store = []

class CandleData(BaseModel):
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    rsi: Optional[float] = None
    ma20: Optional[float] = None
    ma50: Optional[float] = None
    ma200: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    atr: Optional[float] = None
    recent_highs: Optional[list[float]] = None
    recent_lows: Optional[list[float]] = None

class AnalysisResponse(BaseModel):
    symbol: str
    timeframe: str
    timestamp: str
    signal: str
    trend: str
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    support_levels: list[float] = []
    resistance_levels: list[float] = []
    summary: str
    confidence: int

async def send_telegram(analysis):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    signal_emoji = {"BUY": "🟢", "SELL": "🔴", "NEUTRAL": "🟡"}.get(analysis.signal, "⚪")
    
    msg = f"""
{signal_emoji} *{analysis.symbol} | {analysis.timeframe}*
━━━━━━━━━━━━━━━
📊 *Signal:* {analysis.signal}
📈 *Trend:* {analysis.trend}
🎯 *Confidence:* {analysis.confidence}%

💰 *Entry:* {analysis.entry or 'N/A'}
🛑 *Stop Loss:* {analysis.stop_loss or 'N/A'}
✅ *Take Profit:* {analysis.take_profit or 'N/A'}

📝 {analysis.summary}
━━━━━━━━━━━━━━━
🕐 {analysis.timestamp}
"""

    async with httpx.AsyncClient() as c:
        await c.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown"
            }
        )

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_market(data: CandleData):
    prompt = f"""
أنت محلل فوركس خبير. حلل هذه البيانات وأعطني تحليلاً دقيقاً.

الزوج: {data.symbol} | الإطار الزمني: {data.timeframe}

بيانات الشمعة الحالية:
- Open: {data.open} | High: {data.high} | Low: {data.low} | Close: {data.close}
- Volume: {data.volume}

المؤشرات الفنية:
- RSI: {data.rsi or 'غير متوفر'}
- MA20: {data.ma20 or 'غير متوفر'} | MA50: {data.ma50 or 'غير متوفر'} | MA200: {data.ma200 or 'غير متوفر'}
- MACD: {data.macd or 'غير متوفر'} | Signal: {data.macd_signal or 'غير متوفر'}
- ATR: {data.atr or 'غير متوفر'}
- Recent Highs: {data.recent_highs or 'غير متوفر'}
- Recent Lows: {data.recent_lows or 'غير متوفر'}

أجب فقط بـ JSON بهذا الشكل بدون أي نص إضافي:
{{
  "signal": "BUY أو SELL أو NEUTRAL",
  "trend": "وصف الاتجاه باختصار",
  "entry": سعر الدخول المقترح أو null,
  "stop_loss": سعر الوقف أو null,
  "take_profit": سعر الهدف أو null,
  "support_levels": [مستوى1, مستوى2],
  "resistance_levels": [مستوى1, مستوى2],
  "summary": "ملخص التحليل بـ 2-3 جمل بالعربي",
  "confidence": رقم من 0 إلى 100
}}
"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        import json
        raw = message.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        analysis = AnalysisResponse(
            symbol=data.symbol,
            timeframe=data.timeframe,
            timestamp=datetime.utcnow().isoformat(),
            **result
        )

        analyses_store.append(analysis.dict())
        if len(analyses_store) > 100:
            analyses_store.pop(0)

        await send_telegram(analysis)

        return analysis

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history")
async def get_history(limit: int = 20):
    return {"analyses": analyses_store[-limit:]}

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
