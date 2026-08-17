import requests
import time
import csv
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from plyer import notification

history_file = Path("bitcoin_history.csv")

print("Sentinel AI is starting...")
print("Watching Bitcoin with multi-timeframe intelligence.")
print("Press Ctrl + C to stop.\n")


def send_notification(title, message):
    notification.notify(title=title, message=message, timeout=10)


def load_history():
    history = []

    if history_file.exists():
        with open(history_file, "r") as file:
            reader = csv.DictReader(file)

            for row in reader:
                history.append({
                    "timestamp": datetime.strptime(
                        row["timestamp"], "%Y-%m-%d %H:%M:%S"
                    ),
                    "price": float(row["price"])
                })

    return history


def get_price_from_minutes_ago(history, minutes, current_time):
    target_time = current_time - timedelta(minutes=minutes)

    closest = min(
        history,
        key=lambda row: abs(row["timestamp"] - target_time)
    )

    if abs(closest["timestamp"] - target_time) <= timedelta(minutes=2):
        return closest["price"]

    return None


def movement_percent(current_price, old_price):
    return ((current_price - old_price) / old_price) * 100


def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None

    series = pd.Series(prices)
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    average_gain = gains.rolling(period).mean().iloc[-1]
    average_loss = losses.rolling(period).mean().iloc[-1]

    if average_loss == 0:
        return 100

    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))


def get_trend(prices, short_period=5, long_period=20):
    if len(prices) < long_period:
        return "COLLECTING", None, None

    series = pd.Series(prices)
    short_ma = series.rolling(short_period).mean().iloc[-1]
    long_ma = series.rolling(long_period).mean().iloc[-1]

    if short_ma > long_ma:
        return "BULLISH", short_ma, long_ma
    elif short_ma < long_ma:
        return "BEARISH", short_ma, long_ma

    return "NEUTRAL", short_ma, long_ma


def get_timeframe_prices(history, minutes):
    """
    Samples the full history into candles/points of approximately
    the requested timeframe.
    """
    if not history:
        return []

    dataframe = pd.DataFrame(history)
    dataframe = dataframe.set_index("timestamp")

    sampled = dataframe["price"].resample(f"{minutes}min").last().dropna()

    return sampled.tolist()


def get_sentinel_verdict(rsi, trends, change_15, change_60):
    score = 50
    reasons = []

    bullish_count = list(trends.values()).count("BULLISH")
    bearish_count = list(trends.values()).count("BEARISH")

    # Multi-timeframe trend confirmation
    if bullish_count == 4:
        score += 30
        reasons.append("all timeframes are bullish")
    elif bullish_count == 3:
        score += 20
        reasons.append("most timeframes are bullish")
    elif bullish_count == 2:
        score += 10
        reasons.append("short-term bullish confirmation")
    elif bearish_count == 4:
        score -= 30
        reasons.append("all timeframes are bearish")
    elif bearish_count == 3:
        score -= 20
        reasons.append("most timeframes are bearish")
    elif bearish_count == 2:
        score -= 10
        reasons.append("bearish confirmation across timeframes")

    # Main 1-minute trend
    main_trend = trends["1m"]

    # RSI in context
    if rsi is not None:
        if main_trend == "BULLISH":
            if rsi < 35:
                score += 20
                reasons.append("strong pullback within bullish trend")
            elif rsi < 50:
                score += 15
                reasons.append("healthy pullback within bullish trend")
            elif rsi <= 70:
                score += 10
                reasons.append("healthy bullish momentum")
            elif rsi <= 80:
                score -= 5
                reasons.append("bullish market becoming overextended")
            else:
                score -= 15
                reasons.append("extremely overbought — do not chase")

        elif main_trend == "BEARISH":
            if rsi > 65:
                score -= 10
                reasons.append("bearish trend with weak overbought bounce")
            elif rsi >= 40:
                score -= 10
                reasons.append("bearish momentum remains in control")
            elif rsi < 30:
                score += 5
                reasons.append("oversold — possible bounce")

    # Momentum confirmation
    if change_15 is not None:
        if change_15 > 0.3 and bullish_count >= 2:
            score += 5
            reasons.append("15-minute momentum confirms bulls")
        elif change_15 < -0.3 and bearish_count >= 2:
            score -= 5
            reasons.append("15-minute momentum confirms bears")

    if change_60 is not None:
        if change_60 > 0.5 and bullish_count >= 2:
            score += 10
            reasons.append("1-hour momentum confirms bulls")
        elif change_60 < -0.5 and bearish_count >= 2:
            score -= 10
            reasons.append("1-hour momentum confirms bears")

    score = max(0, min(100, score))

    # Final verdict
    if bullish_count >= 3 and rsi is not None and rsi > 80:
        verdict = "BULLISH — WAIT FOR PULLBACK"
    elif score >= 80:
        verdict = "STRONG BUY SETUP"
    elif score >= 65:
        verdict = "BULLISH BIAS"
    elif score <= 20:
        verdict = "STRONG SELL / AVOID"
    elif score <= 40:
        verdict = "BEARISH BIAS"
    else:
        verdict = "WAIT"

    return score, verdict, reasons


history = load_history()

print(f"Loaded {len(history)} previous price readings.\n")

while True:
    try:
        url = "https://api.coinbase.com/v2/prices/BTC-GBP/spot"
        data = requests.get(url, timeout=10).json()

        price = float(data["data"]["amount"])
        timestamp = datetime.now()

        history.append({
            "timestamp": timestamp,
            "price": price
        })

        with open(history_file, "a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                price
            ])

        print("\n" + "=" * 60)
        print(timestamp.strftime("%Y-%m-%d %H:%M:%S"))
        print(f"BITCOIN: £{price:,.2f}")
        print("-" * 60)

        # Price movements
        movements = {}

        for minutes, label in [(15, "15m"), (60, "1h"), (1440, "24h")]:
            old_price = get_price_from_minutes_ago(
                history, minutes, timestamp
            )

            if old_price is not None:
                movements[label] = movement_percent(price, old_price)
                print(f"{label} movement: {movements[label]:+.2f}%")
            else:
                movements[label] = None
                print(f"{label} movement: Waiting for data")

        # 1-minute data
        prices_1m = [row["price"] for row in history]

        # Multi-timeframe sampled data
        prices_5m = get_timeframe_prices(history, 5)
        prices_15m = get_timeframe_prices(history, 15)
        prices_60m = get_timeframe_prices(history, 60)

        # RSI from 1-minute data
        rsi = calculate_rsi(prices_1m)

        # Trends from each timeframe
        trends = {}

        trends["1m"], _, _ = get_trend(prices_1m)
        trends["5m"], _, _ = get_trend(prices_5m)
        trends["15m"], _, _ = get_trend(prices_15m)
        trends["1h"], _, _ = get_trend(prices_60m)

        score, verdict, reasons = get_sentinel_verdict(
            rsi,
            trends,
            movements["15m"],
            movements["1h"]
        )

        print("\n--- MULTI-TIMEFRAME INTELLIGENCE ---")

        print(f"RSI (1m): {rsi:.1f}" if rsi is not None else "RSI: Collecting")
        print()
        print(f"1m Trend:  {trends['1m']}")
        print(f"5m Trend:  {trends['5m']}")
        print(f"15m Trend: {trends['15m']}")
        print(f"1h Trend:  {trends['1h']}")

        print("\n" + "=" * 60)
        print(f"SENTINEL SCORE: {score}/100")
        print(f"VERDICT: {verdict}")

        if reasons:
            print("\nWHY:")
            for reason in reasons:
                print(f"- {reason}")

        print("=" * 60)

        # Only alert for genuinely strong setups
        if verdict in ["STRONG BUY SETUP", "STRONG SELL / AVOID"]:
            message = (
                f"{verdict} | Score: {score}/100 | "
                f"BTC: £{price:,.0f}"
            )
            send_notification("Sentinel AI Signal", message)

    except Exception as error:
        print(f"Error getting Bitcoin price: {error}")

    time.sleep(60)