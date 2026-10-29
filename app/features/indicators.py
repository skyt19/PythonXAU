"""
Technical indicators for feature engineering.
"""
import numpy as np
import pandas as pd
import pandas_ta as ta


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate technical indicators.

    Args:
        df: DataFrame with OHLC data

    Returns:
        DataFrame with indicators added
    """
    df = df.copy()

    # EMAs
    df['ema_20'] = ta.ema(df['close'], length=20)
    df['ema_50'] = ta.ema(df['close'], length=50)
    df['ema_200'] = ta.ema(df['close'], length=200)

    # ATR
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)

    # ADX and Directional Indicators
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    if adx_df is not None:
        df = pd.concat([df, adx_df], axis=1)

    # RSI
    df['rsi'] = ta.rsi(df['close'], length=14)

    # Returns
    df['returns'] = df['close'].pct_change()
    df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

    # Volatility (realized)
    df['realized_vol'] = df['returns'].rolling(20).std()

    # Price position relative to EMAs
    df['price_vs_ema20'] = (df['close'] - df['ema_20']) / df['close']
    df['price_vs_ema50'] = (df['close'] - df['ema_50']) / df['close']

    # EMA trends
    df['ema_trend_short'] = (df['ema_20'] > df['ema_50']).astype(int)
    df['ema_trend_long'] = (df['ema_50'] > df['ema_200']).astype(int)

    # Candle features
    df['body'] = abs(df['close'] - df['open'])
    df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
    df['range'] = df['high'] - df['low']

    # High-low spread (typical for M15 gold)
    df['spread'] = df['high'] - df['low']
    df['spread_normalized'] = df['spread'] / df['close']

    return df


def calculate_features_for_ml(df: pd.DataFrame, lookback: int = 64) -> pd.DataFrame:
    """
    Calculate features specifically for ML model.

    Args:
        df: DataFrame with indicators
        lookback: Number of historical bars to use

    Returns:
        DataFrame with ML features
    """
    df = df.copy()

    # Ensure we have enough data
    if len(df) < lookback + 200:  # Need extra for EMAs
        raise ValueError(f"Insufficient data: need {lookback + 200}, got {len(df)}")

    # Calculate all indicators
    df = calculate_indicators(df)

    # Drop NaN rows from indicator calculations
    df = df.dropna()

    # Select feature columns for ML
    feature_columns = [
        'returns',
        'log_returns',
        'realized_vol',
        'ema_trend_short',
        'ema_trend_long',
        'price_vs_ema20',
        'price_vs_ema50',
        'atr',
        'ADX_14',
        'DMP_14',
        'DMN_14',
        'rsi',
        'body',
        'range',
        'spread_normalized',
    ]

    # Filter to existing columns
    feature_columns = [col for col in feature_columns if col in df.columns]

    return df[['timestamp'] + feature_columns]
