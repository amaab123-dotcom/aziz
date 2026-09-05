"""
طبقة تخزين نتائج التصنيف والفلترة — PostgreSQL.

تحويل عن نسخة SQLite السابقة، لأن SQLite لا يصلح للإنتاج على منصات مثل
Railway/Render (الملف يُمسح عند كل إعادة تشغيل في الخطة المجانية).

يقرأ رابط الاتصال من متغير البيئة DATABASE_URL — هذا هو الاسم القياسي
الذي تحقنه Railway وRender تلقائياً عند ربط قاعدة بيانات Postgres
بمشروعك، فلا تحتاج تكتبه يدوياً في الكود.

⚠️ تنبيه: هذا الكود لم يُختبر ضد خادم PostgreSQL فعلي (البيئة التي كُتب
فيها بدون اتصال إنترنت ولا تثبيت psycopg2). اختبره بنفسك على قاعدة
بيانات حقيقية قبل الاعتماد عليه في الإنتاج.

يتطلب: pip install psycopg2-binary
"""

import os
import json
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor


def init_db(database_url: str = None):
    """
    يفتح اتصالاً بقاعدة بيانات Postgres وينشئ الجداول إن لم تكن موجودة.
    database_url: إن لم يُمرَّر، يُقرأ من متغير البيئة DATABASE_URL.
    """
    database_url = database_url or os.environ["DATABASE_URL"]
    conn = psycopg2.connect(database_url)

    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS filter_results (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                final_direction TEXT NOT NULL,
                consensus_pct TEXT NOT NULL,
                school_details JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (symbol, timeframe)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS excluded_results (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                reason TEXT NOT NULL,
                school_details JSONB,
                updated_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (symbol, timeframe)
            )
        """)
    conn.commit()
    return conn


def save_watchlist_results(conn, timeframe: str, watchlist_result: dict) -> None:
    """
    يحفظ مخرجات classify_watchlist في قاعدة البيانات لفاصل زمني محدد.
    نفس منطق نسخة SQLite تماماً: كل سهم يُحدَّث في مكانه الصحيح، ويُزال
    تلقائياً من الجدول الآخر إذا تغيّرت حالته بين مؤهل ومستبعد.
    """
    now = datetime.now(timezone.utc)

    with conn.cursor() as cur:
        for direction in ("صاعد", "هابط"):
            for stock in watchlist_result[direction]:
                cur.execute("""
                    INSERT INTO filter_results
                        (symbol, timeframe, final_direction, consensus_pct, school_details, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, timeframe) DO UPDATE SET
                        final_direction = EXCLUDED.final_direction,
                        consensus_pct = EXCLUDED.consensus_pct,
                        school_details = EXCLUDED.school_details,
                        updated_at = EXCLUDED.updated_at
                """, (
                    stock["الرمز"], timeframe, direction, stock["نسبة التوافق"],
                    json.dumps(stock["تفاصيل المدارس"], ensure_ascii=False), now,
                ))
                cur.execute(
                    "DELETE FROM excluded_results WHERE symbol = %s AND timeframe = %s",
                    (stock["الرمز"], timeframe),
                )

        for stock in watchlist_result["مستبعد"]:
            cur.execute("""
                INSERT INTO excluded_results
                    (symbol, timeframe, reason, school_details, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (symbol, timeframe) DO UPDATE SET
                    reason = EXCLUDED.reason,
                    school_details = EXCLUDED.school_details,
                    updated_at = EXCLUDED.updated_at
            """, (
                stock["الرمز"], timeframe, stock["السبب"],
                json.dumps(stock.get("تفاصيل المدارس", {}), ensure_ascii=False), now,
            ))
            cur.execute(
                "DELETE FROM filter_results WHERE symbol = %s AND timeframe = %s",
                (stock["الرمز"], timeframe),
            )

    conn.commit()


def get_filtered_stocks(conn, timeframe: str, direction: str) -> list:
    """يُرجع كل الأسهم المؤهلة لفاصل زمني واتجاه محددين، الأحدث تحديثاً أولاً."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT symbol, consensus_pct, updated_at
            FROM filter_results
            WHERE timeframe = %s AND final_direction = %s
            ORDER BY updated_at DESC
        """, (timeframe, direction))
        rows = cur.fetchall()

    return [
        {"الرمز": r["symbol"], "نسبة التوافق": r["consensus_pct"], "آخر تحديث": r["updated_at"].isoformat()}
        for r in rows
    ]


def get_excluded_stocks(conn, timeframe: str) -> list:
    """يُرجع كل الأسهم المستبعدة لفاصل زمني محدد، مع السبب."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT symbol, reason, updated_at
            FROM excluded_results
            WHERE timeframe = %s
            ORDER BY updated_at DESC
        """, (timeframe,))
        rows = cur.fetchall()

    return [
        {"الرمز": r["symbol"], "السبب": r["reason"], "آخر تحديث": r["updated_at"].isoformat()}
        for r in rows
    ]
