"""
منصة تصنيف الأسهم — خادم الويب الرئيسي.

يعمل بمكتبات بايثون القياسية فقط (بدون FastAPI/Flask) حتى يشتغل مباشرة
بدون تثبيت أي شيء إضافي:

    python3 platform_app.py

ثم افتح المتصفح على: http://127.0.0.1:8000
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import storage

# متغير المنفذ يُحقن من Railway/Render وقت التشغيل. مسار/رابط قاعدة
# البيانات صار عبر storage.init_db نفسها (تقرأ DATABASE_URL داخلياً بعد
# التحويل إلى PostgreSQL) بدل الاتصال المباشر السابق بـ SQLite هنا.
PORT = int(os.environ.get("PORT", 8000))
TIMEFRAMES = ["يومي", "أسبوعي", "شهري", "سنوي", "10 سنوات"]


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<title>منصة تصنيف الأسهم</title>
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { font-family: Tahoma, Arial, sans-serif; background: #f1efe8; margin: 0; padding: 20px; color: #2c2c2a; max-width: 640px; margin-inline: auto; }
  h1 { font-size: 18px; font-weight: 500; margin: 0 0 4px; }
  .updated { font-size: 12px; color: #888780; margin-bottom: 20px; }
  .tf-card { background: #fff; border: 1px solid #d3d1c7; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
  .tf-title { font-weight: 500; font-size: 15px; margin: 0 0 10px; }
  .row { display: flex; gap: 8px; }
  .pill { flex: 1; display: flex; align-items: center; justify-content: space-between; border-radius: 8px; padding: 12px 14px; cursor: pointer; min-height: 44px; -webkit-user-select: none; user-select: none; }
  .pill:active { opacity: 0.7; }
  .pill-up { background: #eaf3de; color: #27500a; }
  .pill-down { background: #fcebeb; color: #791f1f; }
  .pill span:first-child { font-size: 14px; }
  .pill span:last-child { font-weight: 500; font-size: 16px; }
  .stock-list { display: none; margin-top: 10px; font-size: 13px; }
  .stock-list.open { display: block; }
  .stock-row { display: flex; justify-content: space-between; padding: 10px 2px; border-top: 1px solid #eee; font-size: 13px; }
  @media (max-width: 360px) {
    body { padding: 12px; }
    .tf-card { padding: 12px; }
  }
</style>
</head>
<body>
  <h1>منصة تصنيف الأسهم — تداول</h1>
  <div class="updated" id="updated">جارِ التحميل...</div>
  <div id="cards"></div>

<script>
const TIMEFRAMES = ["يومي", "أسبوعي", "شهري", "سنوي", "10 سنوات"];

async function loadAll() {
  const container = document.getElementById('cards');
  container.innerHTML = '';
  let latestUpdate = '';
  let hadError = false;

  for (const tf of TIMEFRAMES) {
    try {
      const res = await fetch(`/api/screener/${encodeURIComponent(tf)}`);
      if (!res.ok) throw new Error('استجابة غير ناجحة: ' + res.status);
      const data = await res.json();

      const card = document.createElement('div');
      card.className = 'tf-card';
      card.innerHTML = `
        <p class="tf-title">${tf}</p>
        <div class="row">
          <div class="pill pill-up" onclick="toggleList('${tf}-up')">
            <span>صاعد</span><span>${data.صاعد.length}</span>
          </div>
          <div class="pill pill-down" onclick="toggleList('${tf}-down')">
            <span>هابط</span><span>${data.هابط.length}</span>
          </div>
        </div>
        <div class="stock-list" id="${tf}-up">
          ${data.صاعد.map(s => `<div class="stock-row"><span>${s.الرمز}</span><span>${s['نسبة التوافق']}</span></div>`).join('') || '<div class="stock-row">لا توجد أسهم مؤهلة حالياً</div>'}
        </div>
        <div class="stock-list" id="${tf}-down">
          ${data.هابط.map(s => `<div class="stock-row"><span>${s.الرمز}</span><span>${s['نسبة التوافق']}</span></div>`).join('') || '<div class="stock-row">لا توجد أسهم مؤهلة حالياً</div>'}
        </div>
      `;
      container.appendChild(card);

      const allDates = [...data.صاعد, ...data.هابط].map(s => s['آخر تحديث']).filter(Boolean);
      if (allDates.length) latestUpdate = allDates.sort().pop();
    } catch (err) {
      hadError = true;
      const card = document.createElement('div');
      card.className = 'tf-card';
      card.innerHTML = `<p class="tf-title">${tf}</p><p style="font-size:13px;color:#791f1f;margin:0;">تعذّر تحميل البيانات — تحقق من الاتصال بالخادم</p>`;
      container.appendChild(card);
    }
  }

  if (hadError) {
    document.getElementById('updated').textContent = 'حدث خلل أثناء التحميل — اسحب للتحديث أو أعد فتح الصفحة';
  } else {
    document.getElementById('updated').textContent = latestUpdate
      ? `آخر تحديث: ${latestUpdate}`
      : 'لا توجد بيانات مخزَّنة بعد — شغّل scheduler.py أولاً';
  }
}

function toggleList(id) {
  document.getElementById(id).classList.toggle('open');
}

loadAll();
</script>
</body>
</html>
"""


_conn = None  # اتصال واحد يُعاد استخدامه بدل فتح اتصال جديد لكل طلب،
              # لأن فتح اتصال TCP لخادم Postgres بعيد على كل طلب HTTP
              # مكلف وبطيء بشكل ملحوظ مقارنة بملف SQLite المحلي السابق


def get_screener_json(timeframe: str) -> dict:
    global _conn
    if _conn is None or _conn.closed:
        _conn = storage.init_db()

    return {
        "صاعد": storage.get_filtered_stocks(_conn, timeframe, "صاعد"),
        "هابط": storage.get_filtered_stocks(_conn, timeframe, "هابط"),
        "مستبعد": storage.get_excluded_stocks(_conn, timeframe),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # تعطيل سجل الطلبات الافتراضي المزعج في الطرفية

    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_html(DASHBOARD_HTML)
            return

        if path.startswith("/api/screener/"):
            timeframe = path[len("/api/screener/"):]
            timeframe = parse_qs(f"tf={timeframe}")["tf"][0]  # فك ترميز URL للعربية
            if timeframe not in TIMEFRAMES:
                self._send_json({"خطأ": f"فاصل غير معروف: {timeframe}"}, status=400)
                return
            self._send_json(get_screener_json(timeframe))
            return

        self._send_json({"خطأ": "مسار غير موجود"}, status=404)


def get_local_ip() -> str:
    """يحدد عنوان IP المحلي للجهاز على الشبكة (بدون اتصال إنترنت فعلي)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # لا يُرسل أي بيانات فعلياً، فقط لتحديد الواجهة
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def run_server(port: int = None):
    port = port or PORT

    # تشغيل المجدول (scheduler.run_forever) كخيط بالخلفية داخل نفس العملية،
    # بدل خدمة worker منفصلة على Railway/Render. هذا يبسّط النشر إلى خدمة
    # واحدة فقط. لا يوقف الموقع لو فشلت دورة تصنيف (نفس منطق العزل
    # الموجود أصلاً داخل scheduler.run_forever نفسها).
    if os.environ.get("RUN_SCHEDULER_IN_BACKGROUND", "1") == "1":
        import threading
        import scheduler as _scheduler
        threading.Thread(target=_scheduler.run_forever, daemon=True).start()
        print("تشغيل المجدول تلقائياً بالخلفية (خدمة واحدة فقط بدل اثنتين).")

    # الاستماع على كل واجهات الشبكة (0.0.0.0) — إلزامي لعمل المنصة على
    # Railway/Render، وأيضاً يسمح بالوصول من الجوال محلياً كما سبق
    server = HTTPServer(("0.0.0.0", port), Handler)
    local_ip = get_local_ip()
    print("المنصة تعمل الآن. افتحها من:")
    print(f"  على نفس الجهاز:  http://127.0.0.1:{port}")
    print(f"  من جوال أو جهاز آخر على نفس الواي فاي:  http://{local_ip}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
