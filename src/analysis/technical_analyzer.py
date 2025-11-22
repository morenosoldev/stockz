"""
Technical analysis using GPT-4 to interpret technical indicators.

Uses structured technical data (not chart images) for faster, cheaper, and more accurate analysis.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from openai import OpenAI

from src.datasources.base import Attribution, DataSource
from src.datasources.technical import TechnicalData
from src.ops.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class TechnicalAnalysis:
    """Technical analysis result from GPT-4."""

    ticker: str
    as_of_date: date
    overall_signal: str  # BULLISH, BEARISH, NEUTRAL
    signal_strength: float  # 0.0 to 1.0
    key_signals: list[dict[str, Any]]  # List of triggered signals
    price_targets: dict[str, float]  # support, resistance, stop_loss
    risk_assessment: str  # LOW, MEDIUM, HIGH
    summary: str
    confidence: float  # 0.0 to 1.0
    attribution: Attribution  # OpenAI GPT-4 attribution


class TechnicalAnalyzer:
    """Analyzer for interpreting technical data using GPT-4."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        """
        Initialize the technical analyzer.

        Args:
            api_key: OpenAI API key (default: from config)
            model: GPT-4 model to use (default: gpt-4o)
        """
        config = get_config()
        self.api_key = api_key or config.llm.openai_api_key
        self.model = model
        self.client = OpenAI(api_key=self.api_key)

    def analyze_technical_data(self, technical_data: TechnicalData) -> TechnicalAnalysis:
        """
        Analyze technical data using GPT-4.

        Args:
            technical_data: TechnicalData object with calculated indicators

        Returns:
            TechnicalAnalysis with GPT-4 interpretation

        Raises:
            RuntimeError: If GPT-4 API call fails
            ValueError: If GPT-4 response cannot be parsed
        """
        logger.info(
            f"Analyzing technical data for {technical_data.ticker}",
            extra={"ticker": technical_data.ticker, "as_of_date": technical_data.as_of_date},
        )

        # Build prompt with technical data
        prompt = self._build_analysis_prompt(technical_data)

        # Call GPT-4
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional technical analyst with 20 years of experience. Analyze technical data and provide structured trading signals.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=1000,
                response_format={"type": "json_object"},  # Force JSON output
            )

            analysis_json = response.choices[0].message.content
            if not analysis_json:
                raise ValueError("Empty response from GPT-4")

            # Store attribution
            attribution = Attribution(
                source=DataSource.CHATBOT_RESEARCH,
                timestamp=datetime.now(),
                api_endpoint=f"https://api.openai.com/v1/chat/completions (model: {self.model})",
                version="1.0",
            )

            # Parse response
            analysis = self._parse_analysis_response(
                analysis_json, technical_data.ticker, technical_data.as_of_date, attribution
            )

            logger.info(
                f"Technical analysis complete for {technical_data.ticker}",
                extra={
                    "ticker": technical_data.ticker,
                    "signal": analysis.overall_signal,
                    "strength": analysis.signal_strength,
                    "confidence": analysis.confidence,
                },
            )

            return analysis

        except Exception as e:
            logger.error(
                f"Technical analysis failed for {technical_data.ticker}",
                extra={"ticker": technical_data.ticker, "error": str(e)},
                exc_info=True,
            )
            raise RuntimeError(f"GPT-4 analysis failed: {e}") from e

    def _build_analysis_prompt(self, data: TechnicalData) -> str:
        """
        Build the GPT-4 prompt with technical data.

        Args:
            data: TechnicalData object

        Returns:
            Formatted prompt string
        """

        # Helper functions for interpretation
        def rsi_interpretation(rsi: float | None) -> str:
            if rsi is None:
                return "N/A"
            if rsi < 30:
                return "OVERSOLD"
            elif rsi > 70:
                return "OVERBOUGHT"
            else:
                return "NEUTRAL"

        def bb_interpretation(bb_width: float | None) -> str:
            if bb_width is None:
                return "N/A"
            if bb_width < 0.03:
                return "SQUEEZE (volatility breakout coming)"
            elif bb_width > 0.10:
                return "WIDE (high volatility)"
            else:
                return "NORMAL"

        def adx_interpretation(adx: float | None) -> str:
            if adx is None:
                return "N/A"
            if adx > 25:
                return "STRONG TREND"
            elif adx > 20:
                return "MODERATE TREND"
            else:
                return "WEAK/NO TREND"

        def price_position(price: float, sma_200: float | None) -> str:
            if sma_200 is None:
                return "N/A"
            if price > sma_200:
                return "Above SMA(200) - Long-term uptrend"
            else:
                return "Below SMA(200) - Long-term downtrend"

        prompt = f"""
You are analyzing technical data for {data.ticker} as of {data.as_of_date}.

**Current Price**: ${data.current_price:.2f} ({data.price_change_pct:+.2f}% from 90 days ago)

**Trend Indicators:**
- SMA(20): ${data.sma_20:.2f if data.sma_20 else 'N/A'}
- SMA(50): ${data.sma_50:.2f if data.sma_50 else 'N/A'}
- SMA(200): ${data.sma_200:.2f if data.sma_200 else 'N/A'}
- EMA(20): ${data.ema_20:.2f if data.ema_20 else 'N/A'}
- EMA(50): ${data.ema_50:.2f if data.ema_50 else 'N/A'}
- Position: {price_position(data.current_price, data.sma_200)}

**Momentum:**
- RSI(14): {data.rsi:.1f if data.rsi else 'N/A'} ({rsi_interpretation(data.rsi)})
- MACD: {data.macd:.2f if data.macd else 'N/A'}
- MACD Signal: {data.macd_signal:.2f if data.macd_signal else 'N/A'}
- MACD Histogram: {data.macd_histogram:.2f if data.macd_histogram else 'N/A'} ({"Bullish" if data.macd_histogram and data.macd_histogram > 0 else "Bearish" if data.macd_histogram and data.macd_histogram < 0 else "N/A"})
- Stochastic: K={data.stochastic_k:.1f if data.stochastic_k else 'N/A'}, D={data.stochastic_d:.1f if data.stochastic_d else 'N/A'}

**Volatility:**
- Bollinger Bands: Upper=${data.bb_upper:.2f if data.bb_upper else 'N/A'}, Middle=${data.bb_middle:.2f if data.bb_middle else 'N/A'}, Lower=${data.bb_lower:.2f if data.bb_lower else 'N/A'}
- BB Width: {data.bb_width:.4f if data.bb_width else 'N/A'} ({bb_interpretation(data.bb_width)})
- ATR(14): ${data.atr:.2f if data.atr else 'N/A'}

**Trend Strength:**
- ADX(14): {data.adx:.1f if data.adx else 'N/A'} ({adx_interpretation(data.adx)})

**Volume:**
- Current Volume: {data.volume:,}
- 20-day Avg: {data.avg_volume_20d:,if data.avg_volume_20d else 'N/A'}
- Volume Ratio: {data.volume_ratio:.2f if data.volume_ratio else 'N/A'}x

**Support/Resistance:**
- Support: ${data.support_level:.2f if data.support_level else 'N/A'}
- Resistance: ${data.resistance_level:.2f if data.resistance_level else 'N/A'}

Based on this technical data, provide a comprehensive analysis in the following JSON format:

{{
  "overall_signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "signal_strength": 0.0 to 1.0 (how strong is the signal),
  "key_signals": [
    {{"indicator": "RSI", "signal": "OVERSOLD", "weight": 0.8}},
    {{"indicator": "MACD", "signal": "BULLISH_CROSS", "weight": 0.6}}
  ],
  "price_targets": {{
    "support": {data.support_level if data.support_level else data.current_price * 0.95},
    "resistance": {data.resistance_level if data.resistance_level else data.current_price * 1.05},
    "stop_loss": (recommended stop-loss level)
  }},
  "risk_assessment": "LOW" | "MEDIUM" | "HIGH",
  "summary": "2-3 sentence technical summary explaining the signal",
  "confidence": 0.0 to 1.0 (confidence in this analysis)
}}

Important guidelines:
- Consider ALL indicators together, not just one
- RSI < 30 is oversold (potential buy), RSI > 70 is overbought (potential sell)
- MACD histogram > 0 is bullish, < 0 is bearish
- BB width < 0.03 indicates volatility squeeze (breakout coming)
- ADX > 25 indicates strong trend
- Price above SMA(200) is bullish long-term
- Higher volume ratio (> 1.5x) confirms the move
- Be conservative: if signals are mixed, use NEUTRAL
- Assign higher weights to stronger signals (0.8-1.0 for very strong, 0.3-0.5 for weak)
"""
        return prompt

    def _parse_analysis_response(
        self, response_json: str, ticker: str, as_of_date: date, attribution: Attribution
    ) -> TechnicalAnalysis:
        """
        Parse GPT-4 JSON response into TechnicalAnalysis object.

        Args:
            response_json: JSON string from GPT-4
            ticker: Stock ticker
            as_of_date: Analysis date
            attribution: Attribution object

        Returns:
            TechnicalAnalysis object

        Raises:
            ValueError: If JSON is invalid or missing required fields
        """
        try:
            data = json.loads(response_json)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from GPT-4: {response_json}")
            raise ValueError(f"Cannot parse GPT-4 response: {e}") from e

        # Validate required fields
        required_fields = [
            "overall_signal",
            "signal_strength",
            "key_signals",
            "price_targets",
            "risk_assessment",
            "summary",
            "confidence",
        ]
        missing = [field for field in required_fields if field not in data]
        if missing:
            raise ValueError(f"Missing required fields in GPT-4 response: {missing}")

        # Validate signal values
        if data["overall_signal"] not in ["BULLISH", "BEARISH", "NEUTRAL"]:
            logger.warning(
                f"Invalid overall_signal: {data['overall_signal']}, defaulting to NEUTRAL"
            )
            data["overall_signal"] = "NEUTRAL"

        if data["risk_assessment"] not in ["LOW", "MEDIUM", "HIGH"]:
            logger.warning(
                f"Invalid risk_assessment: {data['risk_assessment']}, defaulting to MEDIUM"
            )
            data["risk_assessment"] = "MEDIUM"

        # Clamp numeric values
        signal_strength = max(0.0, min(1.0, float(data["signal_strength"])))
        confidence = max(0.0, min(1.0, float(data["confidence"])))

        return TechnicalAnalysis(
            ticker=ticker,
            as_of_date=as_of_date,
            overall_signal=data["overall_signal"],
            signal_strength=signal_strength,
            key_signals=data["key_signals"],
            price_targets=data["price_targets"],
            risk_assessment=data["risk_assessment"],
            summary=data["summary"],
            confidence=confidence,
            attribution=attribution,
        )
