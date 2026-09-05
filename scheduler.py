"""
المجدول الساعي — يعيد تشغيل التصنيف والفلترة كل ساعة لكل الفواصل الزمنية
الخمسة، ويحفظ النتائج في نفس قاعدة البيانات التي تقرأ منها المنصة
(platform_app.py).

للتشغيل الفعلي المستمر:
    python3 scheduler.py

للتشغيل مرة واحدة فقط (مفيد للاختبار اليدوي):
    python3 -c "from scheduler import run_once; run_once()"
"""

import time
from datetime import datetime, timezone

import storage
from stock_classifier import classify_watchlist, DEFAULT_WATCHLIST, TIMEFRAME_PARAMS

RUN_INTERVAL_SECONDS = 60 * 60  # كل ساعة، بحسب القرار المتفق عليه سابقاً


def run_once(symbols: list = None) -> None:
    """يشغّل دورة تصنيف كاملة (كل الفواصل × كل الأسهم) مرة واحدة."""
    symbols = symbols or DEFAULT_WATCHLIST
    conn = storage.init_db()  # يقرأ DATABASE_URL من متغيرات البيئة تلقائياً

    print(f"[{datetime.now(timezone.utc).isoformat()}] بدء دورة التصنيف...")

    for timeframe in TIMEFRAME_PARAMS:
        result = classify_watchlist(symbols, timeframe=timeframe)
        storage.save_watchlist_results(conn, timeframe, result)
        print(
            f"  {timeframe}: صاعد={len(result['صاعد'])} "
            f"هابط={len(result['هابط'])} مستبعد={len(result['مستبعد'])}"
        )

    conn.close()
    print("انتهت الدورة.")


def run_forever(symbols: list = None, interval_seconds: int = RUN_INTERVAL_SECONDS) -> None:
    """يعيد تشغيل run_once كل ساعة إلى ما لا نهاية."""
    while True:
        try:
            run_once(symbols)
        except Exception as e:
            # عطل في دورة كاملة (مثلاً فقدان الاتصال) لا يوقف المجدول نفسه
            print(f"خطأ في دورة التصنيف: {e}")

        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_forever()
