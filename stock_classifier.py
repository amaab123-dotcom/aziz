"""
نموذج أولي: جلب بيانات سهم من السوق السعودي (تداول) عبر yfinance
وتطبيق مدرسة التحليل الفني الكلاسيكي لتصنيف الاتجاه (صاعد/هابط فقط).

للتشغيل الفعلي تحتاج:
    pip install yfinance pandas numpy

يستخدم رمز الأسهم السعودية بصيغة Yahoo Finance، مثلاً:
    1120.SR = الراجحي
    2222.SR = أرامكو السعودية
    2010.SR = سابك
    7010.SR = الاتصالات السعودية
"""

import pandas as pd
import numpy as np


# الفواصل الزمنية المدعومة. "سنوي" و"10 سنوات" ليسا شموعاً مجمّعة (لا يوجد
# "متوسط 200 سنة" منطقي) — هما نفس شموع الأسعار اليومية/الأسبوعية، لكن
# بنظرة على مدى أطول من تاريخ السهم، بحسب توضيح المستخدم.
TIMEFRAME_PARAMS = {
    "يومي": {"period": "2y", "interval": "1d"},
    "أسبوعي": {"period": "3y", "interval": "1wk"},
    "شهري": {"period": "max", "interval": "1mo"},
    "سنوي": {"period": "6y", "interval": "1wk"},
    "10 سنوات": {"period": "max", "interval": "1wk"},
}

# نوافذ المؤشرات تتناسب مع كل فاصل — استخدام نفس متوسط 50/200 على كل الفواصل
# كان سيجعل "الأسبوعي" و"السنوي" متطابقين تماماً في النتيجة، ويجعل "الشهري"
# يحتاج ~16 سنة تاريخ (غير متوفرة لأغلب أسهم تداول). القيم أدناه بعدد الشموع.
SCHOOL_WINDOWS = {
    "يومي": {"ma_short": 50, "ma_long": 200, "momentum_window": 20, "swing_window": 10},
    "أسبوعي": {"ma_short": 13, "ma_long": 52, "momentum_window": 12, "swing_window": 4},
    "شهري": {"ma_short": 6, "ma_long": 24, "momentum_window": 6, "swing_window": 2},
    "سنوي": {"ma_short": 13, "ma_long": 52, "momentum_window": 26, "swing_window": 4},
    "10 سنوات": {"ma_short": 24, "ma_long": 104, "momentum_window": 52, "swing_window": 6},
}


def fetch_stock_data(symbol: str, timeframe: str = "يومي") -> pd.DataFrame:
    """
    يجلب بيانات السهم من Yahoo Finance للفاصل الزمني المطلوب.
    ملاحظة: يحتاج اتصال إنترنت واستيراد مكتبة yfinance.
    """
    if timeframe not in TIMEFRAME_PARAMS:
        raise NotImplementedError(
            f"الفاصل '{timeframe}' غير مبني بعد — "
            f"المدعوم حالياً: {list(TIMEFRAME_PARAMS.keys())}"
        )

    import yfinance as yf

    params = TIMEFRAME_PARAMS[timeframe]
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=params["period"], interval=params["interval"])

    if df.empty:
        raise ValueError(f"لم يتم العثور على بيانات للرمز: {symbol}")

    return df


def classify_trend_classical_ta(df: pd.DataFrame, ma_short: int = 50, ma_long: int = 200) -> dict:
    """
    مدرسة التحليل الفني الكلاسيكي:
    - متوسط متحرك قصير مقابل متوسط متحرك طويل (Golden/Death Cross)
    - مؤشر القوة النسبية RSI(14) كمؤكد ثانٍ

    نافذتا المتوسطين (ma_short/ma_long) تُمرَّران حسب الفاصل الزمني
    المختار — راجع SCHOOL_WINDOWS.

    القرار ثنائي إجبارياً (صاعد أو هابط) بدون خيار "عرضي"،
    بحسب متطلبات المنصة.
    """
    close = df["Close"]

    ma_s = close.rolling(window=ma_short).mean()
    ma_l = close.rolling(window=ma_long).mean()

    # حساب RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    last_ma_s = ma_s.iloc[-1]
    last_ma_l = ma_l.iloc[-1]
    last_rsi = rsi.iloc[-1]
    last_price = close.iloc[-1]

    # لا يمكن إصدار قرار موثوق إذا لم تتوفر بيانات كافية للمتوسط الطويل
    if pd.isna(last_ma_l) or pd.isna(last_ma_s):
        raise ValueError(
            f"بيانات غير كافية لحساب المتوسط ({ma_long} فترة) — "
            f"يلزم {ma_long} فترة تداول على الأقل لهذه المدرسة على هذا الفاصل"
        )

    # قاعدة القرار الثنائي: المتوسطات هي المرجّح الأساسي، RSI مؤكد فقط
    if last_ma_s >= last_ma_l:
        direction = "صاعد"
    else:
        direction = "هابط"

    # سعر ثابت تماماً (loss=0) يجعل RSI غير معرّف رياضياً؛ يُعتبر 50 (محايد)
    if pd.isna(last_rsi):
        last_rsi = 50.0

    return {
        "الاتجاه": direction,
        "آخر سعر إغلاق": round(float(last_price), 2),
        f"متوسط {ma_short} فترة": round(float(last_ma_s), 2),
        f"متوسط {ma_long} فترة": round(float(last_ma_l), 2),
        "RSI(14)": round(float(last_rsi), 1),
    }


def classify_trend_ichimoku(df: pd.DataFrame) -> dict:
    """
    مدرسة Ichimoku:
    - Tenkan-sen (9) و Kijun-sen (26): زخم قصير/متوسط المدى
    - سحابة Senkou Span A/B (52، مُسقطة 26 يوماً للأمام): الدعم/المقاومة الحالية

    القرار ثنائي إجبارياً:
    - السعر فوق السحابة بالكامل → صاعد
    - السعر تحت السحابة بالكامل → هابط
    - السعر داخل السحابة (حالة غامضة) → يُحسم بمقارنة Tenkan مقابل Kijun
      (لا يوجد خيار "غير محدد" في هذه المنصة)
    """
    high, low, close = df["High"], df["Low"], df["Close"]

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

    last_price = close.iloc[-1]
    last_tenkan = tenkan.iloc[-1]
    last_kijun = kijun.iloc[-1]
    last_span_a = senkou_a.iloc[-1]
    last_span_b = senkou_b.iloc[-1]

    if any(pd.isna(v) for v in [last_tenkan, last_kijun, last_span_a, last_span_b]):
        raise ValueError(
            "بيانات غير كافية لحساب سحابة Ichimoku — "
            "يلزم نحو 78 يوم تداول على الأقل لهذه المدرسة"
        )

    cloud_top = max(last_span_a, last_span_b)
    cloud_bottom = min(last_span_a, last_span_b)

    if last_price > cloud_top:
        direction = "صاعد"
    elif last_price < cloud_bottom:
        direction = "هابط"
    else:
        # السعر داخل السحابة: يُحسم القرار بترجيح Tenkan/Kijun بدل ترك الحالة غامضة
        direction = "صاعد" if last_tenkan >= last_kijun else "هابط"

    return {
        "الاتجاه": direction,
        "آخر سعر إغلاق": round(float(last_price), 2),
        "Tenkan-sen": round(float(last_tenkan), 2),
        "Kijun-sen": round(float(last_kijun), 2),
        "أعلى حد السحابة": round(float(cloud_top), 2),
        "أدنى حد السحابة": round(float(cloud_bottom), 2),
    }


def classify_trend_elliott_wave(df: pd.DataFrame, swing_window: int = 10) -> dict:
    """
    مدرسة موجات إليوت (نسخة مبسطة):
    - تحديد نقاط التأرجح (Swing Highs/Lows) عبر نافذة محلية
    - اتجاه القمم المتتالية واتجاه القيعان المتتالية يحددان الموجة الحالية

    قمم متصاعدة + قيعان متصاعدة → موجة صاعدة (Higher Highs / Higher Lows)
    قمم متناقصة + قيعان متناقصة → موجة هابطة (Lower Highs / Lower Lows)
    عند التعارض: يُحسم القرار بميل الانحدار الخطي لكل نقاط التأرجح مجتمعة
    (قرار ثنائي إجباري، بدون خيار "غير محدد")
    """
    close = df["Close"].reset_index(drop=True)
    n = len(close)

    highs, lows = [], []
    for i in range(swing_window, n - swing_window):
        segment = close.iloc[i - swing_window: i + swing_window + 1]
        if close.iloc[i] == segment.max():
            highs.append((i, close.iloc[i]))
        elif close.iloc[i] == segment.min():
            lows.append((i, close.iloc[i]))

    if len(highs) < 2 or len(lows) < 2:
        raise ValueError(
            "بيانات غير كافية لتحديد نقاط تأرجح موثوقة — "
            "يلزم تاريخ أطول لهذه المدرسة"
        )

    last_two_highs = highs[-2:]
    last_two_lows = lows[-2:]
    higher_highs = last_two_highs[1][1] > last_two_highs[0][1]
    higher_lows = last_two_lows[1][1] > last_two_lows[0][1]

    if higher_highs and higher_lows:
        direction = "صاعد"
    elif not higher_highs and not higher_lows:
        direction = "هابط"
    else:
        # تعارض بين القمم والقيعان: يُحسم بميل الانحدار الخطي لكل نقاط التأرجح
        swing_points = sorted(highs + lows, key=lambda p: p[0])
        xs = np.array([p[0] for p in swing_points])
        ys = np.array([p[1] for p in swing_points])
        slope = np.polyfit(xs, ys, 1)[0]
        direction = "صاعد" if slope >= 0 else "هابط"

    return {
        "الاتجاه": direction,
        "آخر قمتين": [round(float(p[1]), 2) for p in last_two_highs],
        "آخر قاعين": [round(float(p[1]), 2) for p in last_two_lows],
    }


def classify_trend_quantitative(df: pd.DataFrame, momentum_window: int = 20) -> dict:
    """
    مدرسة التحليل الكمي (نسخة مبسطة):
    - عامل الزخم (Rate of Change) خلال نافذة تتناسب مع الفاصل الزمني كمرجّح أساسي
    - Z-score للسعر الحالي مقابل متوسط 50 فترة كمؤكد

    قرار ثنائي إجباري بناءً على إشارة الزخم.
    """
    close = df["Close"]

    if len(close) <= momentum_window:
        raise ValueError(
            f"بيانات غير كافية لحساب الزخم على {momentum_window} فترة"
        )

    roc = (close.iloc[-1] - close.iloc[-1 - momentum_window]) / close.iloc[-1 - momentum_window] * 100

    ma50 = close.rolling(50).mean()
    std50 = close.rolling(50).std()
    z_score = (close.iloc[-1] - ma50.iloc[-1]) / std50.iloc[-1]

    if pd.isna(z_score):
        raise ValueError("بيانات غير كافية لحساب Z-score — يلزم 50 فترة على الأقل")

    direction = "صاعد" if roc >= 0 else "هابط"

    return {
        "الاتجاه": direction,
        f"الزخم (ROC {momentum_window} فترة) %": round(float(roc), 2),
        "Z-score": round(float(z_score), 2),
    }


def classify_trend_fundamental(financial_metrics: dict) -> dict:
    """
    مدرسة التحليل الأساسي — تحتاج بيانات قوائم مالية فعلية (لم تُربط بعد بمصدر حي).

    financial_metrics المتوقعة مثلاً:
        {"نمو_الأرباح_سنوي": 0.12, "نسبة_مكرر_الربحية_مقابل_القطاع": -0.05}
    (قيمة موجبة = أفضل من متوسط القطاع أو نمو إيجابي)

    هذه دالة جاهزة للتشغيل فور توصيل مصدر بيانات مالي حقيقي
    (مثل إفصاحات تداول أو أرقام)؛ حالياً تتطلب إدخال القيم يدوياً.
    """
    if not financial_metrics:
        raise ValueError(
            "لا يوجد مصدر بيانات مالية موصول بعد لهذه المدرسة — "
            "أدخل financial_metrics يدوياً أو استبعد هذه المدرسة مؤقتاً"
        )

    score = sum(financial_metrics.values())
    direction = "صاعد" if score >= 0 else "هابط"

    return {"الاتجاه": direction, "المدخلات": financial_metrics}


def classify_trend_behavioral(sentiment_score: float | None = None) -> dict:
    """
    مدرسة التحليل السلوكي — تحتاج تحليل مشاعر من الأخبار/السوشال ميديا
    (لم يُربط بعد، مؤجل حسب خطة الـMVP).

    sentiment_score: قيمة بين -1 (سلبي تماماً) و 1 (إيجابي تماماً)،
    ناتجة من نموذج تحليل مشاعر (مثل FinBERT) على الأخبار/المنشورات.
    """
    if sentiment_score is None:
        raise ValueError(
            "لا يوجد مصدر بيانات مشاعر موصول بعد لهذه المدرسة — "
            "أدخل sentiment_score يدوياً أو استبعد هذه المدرسة مؤقتاً"
        )

    direction = "صاعد" if sentiment_score >= 0 else "هابط"
    return {"الاتجاه": direction, "درجة المشاعر": round(float(sentiment_score), 2)}

def check_consensus(school_results: dict) -> dict:
    """
    school_results: قاموس بصيغة {"اسم المدرسة": "صاعد" أو "هابط"}

    يُرجع النتيجة النهائية فقط إذا اتفقت كل المدارس؛ وإلا يُستبعد السهم
    تماماً من القوائم (لا يُصنَّف "عرضي" ولا يظهر بأي شكل).
    """
    directions = set(school_results.values())

    if len(directions) == 1:
        final_direction = directions.pop()
        return {
            "مؤهل": True,
            "الاتجاه النهائي": final_direction,
            "نسبة التوافق": "100%",
            "تفاصيل المدارس": school_results,
        }

    return {
        "مؤهل": False,
        "السبب": "لا يوجد توافق تام بين المدارس — السهم مستبعد من القائمة",
        "تفاصيل المدارس": school_results,
    }


def classify_stock(symbol: str, timeframe: str = "يومي", financial_metrics: dict | None = None,
                    sentiment_score: float | None = None) -> dict:
    """
    نقطة الدخول الرئيسية: تجلب البيانات للفاصل الزمني المطلوب، تُشغّل كل
    المدارس المتاحة حالياً، ثم تُطبّق فحص التوافق التام قبل إصدار قرار نهائي.

    المدارس الأربع المبنية على السعر تعمل دائماً. مدرستا الأساسي والسلوكي
    تُشغَّلان فقط إذا زُوِّدتا ببياناتهما (لأن مصدرهما غير موصول بعد)؛
    وإلا تُستبعدان من فحص التوافق دون التأثير على المدارس الأخرى.
    """
    df = fetch_stock_data(symbol, timeframe=timeframe)
    windows = SCHOOL_WINDOWS[timeframe]

    school_directions = {
        "التحليل الفني الكلاسيكي": classify_trend_classical_ta(
            df, ma_short=windows["ma_short"], ma_long=windows["ma_long"]
        )["الاتجاه"],
        "Ichimoku": classify_trend_ichimoku(df)["الاتجاه"],
        "موجات إليوت": classify_trend_elliott_wave(
            df, swing_window=windows["swing_window"]
        )["الاتجاه"],
        "التحليل الكمي": classify_trend_quantitative(
            df, momentum_window=windows["momentum_window"]
        )["الاتجاه"],
    }

    if financial_metrics is not None:
        school_directions["التحليل الأساسي"] = classify_trend_fundamental(financial_metrics)["الاتجاه"]

    if sentiment_score is not None:
        school_directions["التحليل السلوكي"] = classify_trend_behavioral(sentiment_score)["الاتجاه"]

    consensus = check_consensus(school_directions)
    consensus["الرمز"] = symbol
    return consensus


def classify_watchlist(symbols: list, timeframe: str = "يومي",
                        financial_metrics_map: dict | None = None,
                        sentiment_map: dict | None = None) -> dict:
    """
    يعمّم classify_stock على قائمة أسهم لفاصل زمني واحد محدد.

    financial_metrics_map / sentiment_map: قواميس اختيارية بصيغة
    {"رمز السهم": بياناته}؛ أي سهم غير موجود فيها يعمل بالمدارس
    الأربع المبنية على السعر فقط.

    يُرجع قاموساً بثلاث قوائم:
    - "صاعد": الأسهم المؤهلة بتوافق تام صاعد
    - "هابط": الأسهم المؤهلة بتوافق تام هابط
    - "مستبعد": الأسهم التي لم تحقق توافقاً تاماً أو تعذّر تصنيفها، مع السبب
    """
    financial_metrics_map = financial_metrics_map or {}
    sentiment_map = sentiment_map or {}

    results = {"صاعد": [], "هابط": [], "مستبعد": []}

    for symbol in symbols:
        try:
            result = classify_stock(
                symbol,
                timeframe=timeframe,
                financial_metrics=financial_metrics_map.get(symbol),
                sentiment_score=sentiment_map.get(symbol),
            )
        except Exception as e:
            # عطل في جلب البيانات أو تاريخ غير كافٍ لا يوقف بقية القائمة
            results["مستبعد"].append({"الرمز": symbol, "السبب": str(e)})
            continue

        if result["مؤهل"]:
            entry = {
                "الرمز": symbol,
                "نسبة التوافق": result["نسبة التوافق"],
                "تفاصيل المدارس": result["تفاصيل المدارس"],
            }
            results[result["الاتجاه النهائي"]].append(entry)
        else:
            results["مستبعد"].append({
                "الرمز": symbol,
                "السبب": result["السبب"],
                "تفاصيل المدارس": result["تفاصيل المدارس"],
            })

    return results


# قائمة أولية بأبرز الأسهم القيادية في تداول للاختبار (يمكن توسيعها لاحقاً)
DEFAULT_WATCHLIST = [
    "1120.SR",  # الراجحي
    "2222.SR",  # أرامكو السعودية
    "2010.SR",  # سابك
    "7010.SR",  # الاتصالات السعودية
    "1180.SR",  # الأهلي السعودي
]


if __name__ == "__main__":
    # مثال: تصنيف قائمة أسهم كاملة دفعة واحدة
    watchlist_result = classify_watchlist(DEFAULT_WATCHLIST)

    print(f"صاعد ({len(watchlist_result['صاعد'])}):")
    for stock in watchlist_result["صاعد"]:
        print(f"  {stock['الرمز']} — توافق {stock['نسبة التوافق']}")

    print(f"\nهابط ({len(watchlist_result['هابط'])}):")
    for stock in watchlist_result["هابط"]:
        print(f"  {stock['الرمز']} — توافق {stock['نسبة التوافق']}")

    print(f"\nمستبعد ({len(watchlist_result['مستبعد'])}):")
    for stock in watchlist_result["مستبعد"]:
        print(f"  {stock['الرمز']} — {stock['السبب']}")
