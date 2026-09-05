"""
اختبار رجعي (Backtesting): يقيس هل إشارات "التوافق التام 100%" كانت
صحيحة فعلياً في الماضي أم لا — قبل الوثوق بها على بيانات حية.

الفكرة: نتحرك عبر التاريخ خطوة بخطوة، وفي كل نقطة نطبّق نفس منطق
classify_stock (لكن على بيانات ذلك التاريخ فقط، بدون تسريب معلومات
من المستقبل)، ثم نتحقق: هل تحرك السعر فعلاً بالاتجاه الذي أصدره
النظام خلال أفق زمني محدد بعدها؟
"""

import pandas as pd

from stock_classifier import (
    classify_trend_classical_ta, classify_trend_ichimoku,
    classify_trend_elliott_wave, classify_trend_quantitative,
    SCHOOL_WINDOWS,
)


def run_backtest(df: pd.DataFrame, timeframe: str, horizon: int, step: int = 5) -> dict:
    """
    df: بيانات سعرية تاريخية كاملة (Close, High, Low) — الأقدم أولاً
    timeframe: أحد الفواصل الخمسة (لتحديد نوافذ المدارس المناسبة)
    horizon: كم فترة للأمام نتحقق من صحة الإشارة (مثلاً 5 = خمس شموع قادمة)
    step: كل كم فترة نُصدر إشارة جديدة (لتسريع الاختبار على بيانات طويلة)
    """
    windows = SCHOOL_WINDOWS[timeframe]
    min_len = windows["ma_long"] + 60  # هامش أمان لضمان استقرار كل المؤشرات

    signals = []

    for end_idx in range(min_len, len(df) - horizon, step):
        # نافذة البيانات حتى هذه اللحظة فقط — لا معلومات من المستقبل إطلاقاً
        window_df = df.iloc[:end_idx].reset_index(drop=True)

        try:
            directions = {
                classify_trend_classical_ta(
                    window_df, ma_short=windows["ma_short"], ma_long=windows["ma_long"]
                )["الاتجاه"],
                classify_trend_ichimoku(window_df)["الاتجاه"],
                classify_trend_elliott_wave(window_df, swing_window=windows["swing_window"])["الاتجاه"],
                classify_trend_quantitative(window_df, momentum_window=windows["momentum_window"])["الاتجاه"],
            }
        except ValueError:
            continue  # بيانات غير كافية عند هذه النقطة، تخطَّ

        if len(directions) != 1:
            continue  # لا يوجد توافق تام — لا تصدر إشارة أصلاً (نفس منطق المنصة الحية)

        signal = directions.pop()
        entry_price = df["Close"].iloc[end_idx - 1]
        exit_price = df["Close"].iloc[end_idx - 1 + horizon]
        actual_return_pct = (exit_price - entry_price) / entry_price * 100

        correct = (
            (signal == "صاعد" and actual_return_pct > 0) or
            (signal == "هابط" and actual_return_pct < 0)
        )

        signals.append({"الإشارة": signal, "العائد الفعلي %": round(actual_return_pct, 2), "صحيحة": correct})

    if not signals:
        return {"عدد الإشارات": 0, "ملاحظة": "لم يصدر أي توافق تام خلال فترة الاختبار بأكملها"}

    total = len(signals)
    hits = sum(s["صحيحة"] for s in signals)
    up = [s for s in signals if s["الإشارة"] == "صاعد"]
    down = [s for s in signals if s["الإشارة"] == "هابط"]

    return {
        "عدد الإشارات": total,
        "الدقة الإجمالية %": round(100 * hits / total, 1),
        "عدد إشارات صاعد": len(up),
        "دقة الصاعد %": round(100 * sum(s["صحيحة"] for s in up) / len(up), 1) if up else None,
        "عدد إشارات هابط": len(down),
        "دقة الهابط %": round(100 * sum(s["صحيحة"] for s in down) / len(down), 1) if down else None,
    }
