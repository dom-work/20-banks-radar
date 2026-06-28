#!/usr/bin/env python3
"""
Банковский Радар — агент автоматического обновления данных.
Запускается GitHub Actions по расписанию.
Находит новые PDF отчётности банков, извлекает метрики, обновляет data.json.
"""

import json, re, sys, time, hashlib, os
import urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import pdfplumber
    PDF_OK = True
except ImportError:
    PDF_OK = False
    print("WARN: pdfplumber не установлен, PDF-парсинг недоступен")

MSK    = timezone(timedelta(hours=3))
TODAY  = datetime.now(MSK).strftime("%d.%m.%Y")
NOW    = datetime.now(MSK).strftime("%d.%m.%Y %H:%M МСК")
ROOT   = Path(__file__).parent.parent
OUTPUT = ROOT / "data.json"
CACHE  = ROOT / ".pdf_cache.json"   # хранит хэши уже обработанных PDF

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# ── РЕЕСТР БАНКОВ И ИХ ИСТОЧНИКОВ ОТЧЁТНОСТИ ────────────────────────────
# frequency: "monthly" | "quarterly" | "semi" | "annual"
# pdf_urls: прямые паттерны URL или страницы с перечнем PDF
BANK_REGISTRY = [
  {
    "r":1,"n":"Сбербанк","lo":"С","lc":"#21A038","tp":"state","pub":1,"pf":0,
    "frequency":"monthly",
    "ir_page": "https://www.sberbank.com/ru/investor-relations/reports-and-publications/financial-results",
    "pdf_patterns": [
        "sberbank.com/common/img/uploaded/files/pdf/msfo",
        "sberbank.com/ru/investor-relations",
        "cdn.sberbank.ru",
    ],
    "rss": "https://www.sberbank.com/ru/investor-relations/rss",
    "keywords": ["МСФО","IFRS","чистая прибыль","ROE","NIM"],
  },
  {
    "r":2,"n":"ВТБ","lo":"В","lc":"#003087","tp":"state","pub":1,"pf":0,
    "frequency":"monthly",
    "ir_page": "https://www.vtb.ru/ir/statements/results/",
    "pdf_patterns": [
        "vtb.ru/ir",
        "cdn.financemarker.ru/reports",
    ],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE","NIM","CIR"],
  },
  {
    "r":3,"n":"Газпромбанк","lo":"Г","lc":"#1B4D9A","tp":"state","pub":0,"pf":0,
    "frequency":"quarterly",
    "ir_page": "https://www.gazprombank.ru/press/",
    "pdf_patterns": ["gazprombank.ru","asros.ru/news/members/gazprombank"],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE","NIM"],
  },
  {
    "r":4,"n":"Альфа-Банк","lo":"А","lc":"#EF3124","tp":"private","pub":0,"pf":0,
    "frequency":"semi",
    "ir_page": "https://alfabank.ru/alfa-investor/",
    "pdf_patterns": [
        "alfabank.servicecdn.ru",
        "alfabank.ru",
    ],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE","NIM","CIR"],
  },
  {
    "r":5,"n":"Россельхозбанк","lo":"Р","lc":"#2E7D32","tp":"state","pub":0,"pf":0,
    "frequency":"quarterly",
    "ir_page": "https://www.rshb.ru/about/reports-conclusion/msfo/",
    "pdf_patterns": ["rshb.ru"],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE","NIM","CIR"],
  },
  {
    "r":6,"n":"МКБ","lo":"М","lc":"#7B1FA2","tp":"private","pub":1,"pf":0,
    "frequency":"quarterly",
    "ir_page": "https://ir.mkb.ru/financial-results",
    "pdf_patterns": ["ir.mkb.ru","mkb.ru"],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE","NIM"],
  },
  {
    "r":7,"n":"Т-Технологии","lo":"Т","lc":"#111111","tp":"private","pub":1,"pf":0,
    "frequency":"quarterly",
    "ir_page": "https://t-technologies.ru/results/",
    "pdf_patterns": ["t-technologies.ru","acdn.tinkoff.ru"],
    "rss": None,
    "keywords": ["МСФО","IFRS","прибыль","ROE","NIM","CIR"],
  },
  {
    "r":8,"n":"Совкомбанк","lo":"С","lc":"#E65100","tp":"private","pub":1,"pf":0,
    "frequency":"quarterly",
    "ir_page": "https://sovcombank.ru/about/info",
    "pdf_patterns": ["sovcombank.ru","cdn.financemarker.ru/reports"],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE","NIM","CIR"],
  },
  {
    "r":9,"n":"Банк ДОМ.РФ","lo":"Д","lc":"#1565C0","tp":"state","pub":1,"pf":1,
    "frequency":"quarterly",
    "ir_page": "https://domrfbank.ru/about/information/msfo/",
    "pdf_patterns": ["domrfbank.ru","dom.rf"],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE","NIM","CIR","проектное финансирование"],
  },
  {
    "r":10,"n":"ПСБ","lo":"П","lc":"#AD1457","tp":"state","pub":0,"pf":0,
    "frequency":"semi",
    "ir_page": "https://www.psbank.ru/Bank/Investors/IFRS",
    "pdf_patterns": ["psbank.ru"],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE"],
  },
  {
    "r":11,"n":"Юникредит Банк","lo":"U","lc":"#c00000","tp":"foreign","pub":0,"pf":0,
    "frequency":"semi",
    "ir_page": None,
    "pdf_patterns": [],
    "rss": None,
    "keywords": [],
    "status_override": "exit",
  },
  {
    "r":12,"n":"БСПБ","lo":"Б","lc":"#0D47A1","tp":"private","pub":1,"pf":0,
    "frequency":"monthly",
    "ir_page": "https://www.bspb.ru/investors/financial-statements/IFRS",
    "pdf_patterns": ["cdn.bspb.ru","bspb.ru"],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE","NIM","CIR","CoR"],
  },
  {
    "r":13,"n":"МТС Банк","lo":"М","lc":"#E53935","tp":"private","pub":1,"pf":0,
    "frequency":"quarterly",
    "ir_page": "https://www.mtsbank.ru/investors-and-shareholders/results/",
    "pdf_patterns": ["mtsbank.ru"],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE","NIM","CIR","COR"],
  },
  {
    "r":14,"n":"Уралсиб","lo":"У","lc":"#00695C","tp":"private","pub":0,"pf":0,
    "frequency":"quarterly",
    "ir_page": "https://uralsib.ru/about/investors/",
    "pdf_patterns": ["uralsib.ru"],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE"],
  },
  {
    "r":15,"n":"Ак Барс","lo":"А","lc":"#558B2F","tp":"private","pub":0,"pf":0,
    "frequency":"annual",
    "ir_page": "https://akbars.ru/about/disclosure/",
    "pdf_patterns": ["akbars.ru"],
    "rss": None,
    "keywords": ["МСФО","прибыль","ROE"],
  },
  {
    "r":16,"n":"БМ-Банк","lo":"О","lc":"#4527A0","tp":"state","pub":0,"pf":0,
    "frequency":"annual",
    "ir_page": None,"pdf_patterns":[],"rss":None,"keywords":[],
    "status_override":"nd",
  },
  {
    "r":17,"n":"Банк Россия","lo":"Р","lc":"#1A237E","tp":"private","pub":0,"pf":0,
    "frequency":"annual",
    "ir_page": None,"pdf_patterns":[],"rss":None,"keywords":[],
    "status_override":"nd",
  },
  {
    "r":18,"n":"Промсвязьбанк","lo":"П","lc":"#F57F17","tp":"state","pub":0,"pf":0,
    "frequency":"semi",
    "ir_page": "https://www.psbank.ru/Bank/Investors/IFRS",
    "pdf_patterns": ["psbank.ru"],
    "rss": None,
    "keywords": ["МСФО","прибыль"],
    "status_override":"loss",
  },
  {
    "r":19,"n":"Экспобанк","lo":"Э","lc":"#006064","tp":"private","pub":0,"pf":0,
    "frequency":"annual",
    "ir_page": None,"pdf_patterns":[],"rss":None,"keywords":[],
    "status_override":"nd",
  },
  {
    "r":20,"n":"Синара Банк","lo":"С","lc":"#37474F","tp":"private","pub":0,"pf":0,
    "frequency":"annual",
    "ir_page": None,"pdf_patterns":[],"rss":None,"keywords":[],
    "status_override":"nd",
  },
]

# ── БАЗОВЫЕ ЗНАЧЕНИЯ (последние известные МСФО 2025) ─────────────────────
BASE_METRICS = {
    1:  {"roe":22.7,"nim":6.2,"cir":30.3,"cor":1.3,"h20":14.6,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"data","src":"МСФО фев.2026"},
    2:  {"roe":18.3,"nim":1.4,"cir":47.3,"cor":1.1,"h20":9.8, "re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"data","src":"МСФО фев.2026"},
    3:  {"roe":10.1,"nim":3.0,"cir":48.6,"cor":None,"h20":11.5,"re":0,"ne":0,"ce":0,"oe":1,"he":1,"st":"part","src":"МСФО мар.2026"},
    4:  {"roe":21.0,"nim":5.8,"cir":42.0,"cor":2.7,"h20":13.0,"re":1,"ne":1,"ce":1,"oe":1,"he":1,"st":"part","src":"МСФО апр.2026"},
    5:  {"roe":14.5,"nim":2.7,"cir":50.0,"cor":None,"h20":12.4,"re":0,"ne":0,"ce":0,"oe":1,"he":1,"st":"part","src":"МСФО мар.2026"},
    6:  {"roe":None,"nim":None,"cir":None,"cor":None,"h20":11.0,"re":0,"ne":0,"ce":0,"oe":0,"he":1,"st":"part","src":"МСФО апр.2026"},
    7:  {"roe":29.1,"nim":10.8,"cir":34.7,"cor":6.5,"h20":12.5,"re":0,"ne":0,"ce":0,"oe":0,"he":1,"st":"data","src":"МСФО мар.2026"},
    8:  {"roe":15.0,"nim":5.3,"cir":57.0,"cor":2.5,"h20":13.0,"re":0,"ne":0,"ce":0,"oe":0,"he":1,"st":"data","src":"МСФО мар.2026"},
    9:  {"roe":21.6,"nim":3.7,"cir":28.3,"cor":0.7,"h20":13.5,"re":0,"ne":0,"ce":0,"oe":0,"he":1,"st":"data","src":"МСФО фев.2026"},
    10: {"roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"loss","src":"убыток −19.1 млрд"},
    11: {"roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"exit","src":"уход до сер.2026"},
    12: {"roe":18.1,"nim":7.4,"cir":29.0,"cor":2.0,"h20":14.0,"re":0,"ne":1,"ce":1,"oe":1,"he":1,"st":"data","src":"МСФО мар.2026"},
    13: {"roe":14.5,"nim":7.2,"cir":35.7,"cor":5.5,"h20":12.0,"re":0,"ne":0,"ce":0,"oe":1,"he":1,"st":"data","src":"МСФО мар.2026"},
    14: {"roe":10.1,"nim":None,"cir":None,"cor":None,"h20":None,"re":1,"ne":0,"ce":0,"oe":0,"he":0,"st":"part","src":"РСБУ апр.2026"},
    15: {"roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"nd","src":"нет данных"},
    16: {"roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"nd","src":"интеграция Открытие"},
    17: {"roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"nd","src":"данные закрыты"},
    18: {"roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"loss","src":"см. ПСБ"},
    19: {"roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"nd","src":"нет данных"},
    20: {"roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"nd","src":"нет данных"},
}

# ── ПАТТЕРНЫ ИЗВЛЕЧЕНИЯ МЕТРИК ────────────────────────────────────────────
METRIC_PATTERNS = {
    "roe": [
        r'(?:ROE|рентабельность\s+(?:собственного\s+)?капитала)[^\d]{0,40}?([\d]+[,.][\d]+)\s*%',
        r'(?:return\s+on\s+equity)[^\d]{0,30}?([\d]+[,.][\d]+)\s*%',
    ],
    "nim": [
        r'(?:NIM|чист(?:ая|ой)\s+процентн(?:ая|ой)\s+марж(?:а|и))[^\d]{0,40}?([\d]+[,.][\d]+)\s*%',
        r'(?:net\s+interest\s+margin)[^\d]{0,30}?([\d]+[,.][\d]+)\s*%',
    ],
    "cir": [
        r'(?:CIR|соотношение\s+расходов\s+(?:к|и)\s+доход\w+|отношение\s+(?:издержек|расходов)\s+к\s+доход\w+)[^\d]{0,40}?([\d]+[,.][\d]+)\s*%',
        r'(?:cost.to.income)[^\d]{0,30}?([\d]+[,.][\d]+)\s*%',
    ],
    "cor": [
        r'(?:COR|Co[Rr]|стоимость\s+риска|cost\s+of\s+risk)[^\d]{0,40}?([\d]+[,.][\d]+)\s*%',
    ],
    "h20": [
        r'(?:H20\.0|Н20\.0|норматив\s+достаточности\s+(?:капитала\s+)?(?:банковской\s+группы)?)[^\d]{0,40}?([\d]+[,.][\d]+)\s*%',
        r'(?:H1\.0|Н1\.0)[^\d]{0,30}?([\d]+[,.][\d]+)\s*%',
    ],
}

# Разумные диапазоны значений для каждой метрики
METRIC_RANGES = {
    "roe": (1.0, 60.0),
    "nim": (0.5, 20.0),
    "cir": (10.0, 90.0),
    "cor": (0.1, 15.0),
    "h20": (8.0, 30.0),
}

# ── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ──────────────────────────────────────────────

def fetch_html(url: str, timeout: int = 20) -> str | None:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            enc = r.headers.get_content_charset() or "utf-8"
            return raw.decode(enc, errors="replace")
    except Exception as e:
        print(f"    WARN fetch {url[:70]}: {e}")
        return None


def fetch_binary(url: str, timeout: int = 30) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        print(f"    WARN fetch_binary {url[:70]}: {e}")
        return None


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text("utf-8"))
        except:
            pass
    return {}


def save_cache(cache: dict):
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), "utf-8")


def extract_number(text: str, patterns: list) -> float | None:
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE | re.MULTILINE):
            try:
                v = float(m.group(1).replace(",", "."))
                return v
            except:
                continue
    return None


def validate_metric(metric: str, value: float) -> bool:
    lo, hi = METRIC_RANGES.get(metric, (0, 1000))
    return lo <= value <= hi


def extract_metrics_from_text(text: str) -> dict:
    """Извлекает все метрики из текста, валидирует диапазоны."""
    found = {}
    for metric, patterns in METRIC_PATTERNS.items():
        val = extract_number(text, patterns)
        if val is not None and validate_metric(metric, val):
            found[metric] = round(val, 2)
    return found


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Извлекает текст из PDF через pdfplumber."""
    if not PDF_OK:
        return ""
    import io
    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            # Берём первые 30 страниц (обычно метрики в начале)
            for page in pdf.pages[:30]:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
    except Exception as e:
        print(f"    WARN pdfplumber: {e}")
    return "\n".join(text_parts)


def find_pdf_links(html: str, base_domain: str, patterns: list) -> list:
    """Находит ссылки на PDF в HTML по паттернам."""
    links = []
    # Ищем все href с .pdf
    all_links = re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', html, re.IGNORECASE)
    for link in all_links:
        # Нормализуем URL
        if link.startswith("//"):
            link = "https:" + link
        elif link.startswith("/"):
            link = base_domain.rstrip("/") + link
        elif not link.startswith("http"):
            link = base_domain.rstrip("/") + "/" + link
        # Проверяем паттерны
        link_lower = link.lower()
        pat_match = any(p.lower() in link_lower for p in patterns) if patterns else True
        msfo_keywords = any(kw in link_lower for kw in [
            "msfo", "мсфо", "ifrs", "financial", "result", "press",
            "отчет", "отчёт", "report", "quarterly", "interim"
        ])
        if (pat_match or msfo_keywords) and link not in links:
            links.append(link)
    return links[:10]  # не более 10 PDF на банк


def determine_status(metrics: dict, bank_reg: dict) -> str:
    if bank_reg.get("status_override"):
        return bank_reg["status_override"]
    if metrics.get("roe") is not None:
        estimated = any([
            bank_reg.get("re"), bank_reg.get("ne"),
            bank_reg.get("ce"), bank_reg.get("oe")
        ])
        return "part" if estimated else "data"
    return "nd"


# ── ОСНОВНАЯ ЛОГИКА ОБРАБОТКИ БАНКА ──────────────────────────────────────

def process_bank(bank_reg: dict, cache: dict, existing_metrics: dict) -> tuple[dict, list]:
    """
    Обрабатывает один банк:
    - Загружает IR-страницу
    - Находит новые PDF
    - Извлекает метрики
    Возвращает (обновлённые метрики, сигналы).
    """
    rank = bank_reg["r"]
    name = bank_reg["n"]
    signals = []

    # Если статус override и нет IR-страницы — пропускаем
    if bank_reg.get("status_override") in ("nd", "exit") and not bank_reg.get("ir_page"):
        return existing_metrics, signals

    metrics = dict(existing_metrics)  # копия
    new_data_found = False

    ir_page = bank_reg.get("ir_page")
    if not ir_page:
        return metrics, signals

    print(f"  [{rank}] {name} — загружаю IR-страницу...")
    html = fetch_html(ir_page)
    if not html:
        print(f"    → страница недоступна")
        return metrics, signals

    # Пробуем сразу извлечь метрики из HTML (пресс-релизы часто в HTML)
    html_text = re.sub(r'<[^>]+>', ' ', html)
    html_text = re.sub(r'\s+', ' ', html_text)
    html_metrics = extract_metrics_from_text(html_text)
    if html_metrics:
        print(f"    → найдено в HTML: {html_metrics}")
        for k, v in html_metrics.items():
            metrics[k] = v
        metrics["src"] = f"Обновлено {TODAY}"
        new_data_found = True

    # Ищем PDF на странице
    domain = re.match(r'https?://[^/]+', ir_page)
    base_domain = domain.group(0) if domain else ""
    pdf_links = find_pdf_links(html, base_domain, bank_reg.get("pdf_patterns", []))
    print(f"    → найдено PDF-ссылок: {len(pdf_links)}")

    for pdf_url in pdf_links[:5]:  # не более 5 PDF на банк
        # Проверяем кэш
        cache_key = md5(pdf_url.encode())
        if cache_key in cache:
            print(f"    → PDF уже обработан: {pdf_url[-60:]}")
            continue

        print(f"    → скачиваю PDF: {pdf_url[-70:]}...")
        pdf_bytes = fetch_binary(pdf_url)
        if not pdf_bytes or len(pdf_bytes) < 10_000:
            print(f"    → PDF слишком маленький или не скачался")
            continue

        # Отмечаем как обработанный
        cache[cache_key] = {"url": pdf_url, "date": TODAY, "bank": name}

        # Извлекаем текст
        pdf_text = extract_pdf_text(pdf_bytes)
        if not pdf_text:
            print(f"    → текст из PDF не извлечён")
            continue

        print(f"    → извлечено {len(pdf_text)} символов")

        # Извлекаем метрики
        pdf_metrics = extract_metrics_from_text(pdf_text)
        if pdf_metrics:
            print(f"    → метрики из PDF: {pdf_metrics}")
            for k, v in pdf_metrics.items():
                metrics[k] = v
            metrics["src"] = f"PDF {TODAY}"
            new_data_found = True

            # Создаём сигнал
            metrics_str = ", ".join(f"{k.upper()}={v}%" for k,v in pdf_metrics.items())
            signals.append({
                "bank": name,
                "logo": bank_reg["lo"],
                "lc": bank_reg["lc"],
                "type": "metric",
                "priority": "high",
                "score": 92,
                "text": f"Новая отчётность МСФО: {metrics_str}. Данные извлечены автоматически из PDF.",
                "tags": list(pdf_metrics.keys()),
                "time": TODAY,
            })

        time.sleep(2)  # пауза между PDF

    if not new_data_found:
        print(f"    → новых данных не найдено, оставляем предыдущие")

    return metrics, signals


# ── KPI И СИГНАЛЫ ─────────────────────────────────────────────────────────

def compute_kpi(banks: list) -> dict:
    roes  = [b["roe"] for b in banks if b.get("roe")]
    rorwa = [b for b in banks if b.get("rorwa")]
    pfcir = [b for b in banks if b.get("pf") and b.get("cir")]
    h20s  = [b for b in banks if b.get("h20")]
    med   = round(sorted(roes)[len(roes)//2], 1) if roes else None
    ldr   = max(rorwa, key=lambda b: b["rorwa"]) if rorwa else None
    bcir  = min(pfcir, key=lambda b: b["cir"])   if pfcir else None
    mnh   = min(h20s,  key=lambda b: b["h20"])   if h20s  else None
    domrf = next((b for b in banks if b["r"]==9), None)
    return {
        "median_roe": med,
        "leader_rorwa_bank":  ldr["n"]    if ldr  else "—",
        "leader_rorwa_val":   ldr["rorwa"]if ldr  else None,
        "best_cir_pf_bank":   bcir["n"]  if bcir else "—",
        "best_cir_pf_val":    bcir["cir"]if bcir else None,
        "min_h20_bank":       mnh["n"]   if mnh  else "—",
        "min_h20_val":        mnh["h20"] if mnh  else None,
        "dom_rf_pf_portfolio": "1.9 трлн",
    }


def build_synthetic_signals(banks: list) -> list:
    sigs = []
    wr = [b for b in banks if b.get("rorwa")]
    if wr:
        top = max(wr, key=lambda b: b["rorwa"])
        sigs.append({
            "bank":top["n"],"logo":top["lo"],"lc":top["lc"],
            "type":"metric","priority":"high","score":95,
            "text":f"Лидер iRoRWA: {top['rorwa']:.2f}% (ROE {top['roe']}% × H20.0 {top['h20']}%). Наилучшая эффективность капитала в ТОП-20.",
            "tags":["iRoRWA","лидер"],"time":TODAY,
        })
    wh = [b for b in banks if b.get("h20")]
    if wh:
        mn = min(wh, key=lambda b: b["h20"])
        sigs.append({
            "bank":mn["n"],"logo":mn["lo"],"lc":mn["lc"],
            "type":"risk","priority":"high" if mn["h20"]<11 else "med","score":85,
            "text":f"Минимальный буфер капитала: H20.0={mn['h20']}% при минимуме 9.25%. Буфер {round(mn['h20']-9.25,2)} пп.",
            "tags":["H20","капитал","риск"],"time":TODAY,
        })
    pf = [b for b in banks if b.get("pf") and b.get("cir")]
    if pf:
        bc = min(pf, key=lambda b: b["cir"])
        sigs.append({
            "bank":bc["n"],"logo":bc["lo"],"lc":bc["lc"],
            "type":"metric","priority":"high","score":90,
            "text":f"Лучший CIR в ПФ: {bc['cir']}%. Эскроу-модель обеспечивает структурно низкий COR={bc.get('cor','—')}%.",
            "tags":["CIR","ПФ","эффективность"],"time":TODAY,
        })
    for b in banks:
        if b.get("st")=="loss":
            sigs.append({
                "bank":b["n"],"logo":b["lo"],"lc":b["lc"],
                "type":"risk","priority":"high","score":88,
                "text":f"Убыток по МСФО: {b.get('src','')}.",
                "tags":["убыток","риск"],"time":TODAY,
            })
    return sigs[:6]


# ── ГЛАВНАЯ ФУНКЦИЯ ──────────────────────────────────────────────────────

def main():
    print(f"{'='*60}")
    print(f"Банковский Радар — агент обновления PDF")
    print(f"Время запуска: {NOW}")
    print(f"pdfplumber: {'доступен' if PDF_OK else 'НЕ установлен'}")
    print(f"{'='*60}\n")

    # Загружаем кэш обработанных PDF
    cache = load_cache()
    print(f"Кэш обработанных PDF: {len(cache)} записей\n")

    # Загружаем предыдущий data.json
    prev_metrics = dict(BASE_METRICS)
    if OUTPUT.exists():
        try:
            prev = json.loads(OUTPUT.read_text("utf-8"))
            for b in prev.get("banks", []):
                r = b.get("r")
                if r in prev_metrics:
                    for f in ["roe","nim","cir","cor","h20","src","st","re","ne","ce","oe","he"]:
                        if b.get(f) is not None:
                            prev_metrics[r][f] = b[f]
            print(f"Предыдущие данные загружены: {prev.get('updated_at','?')}\n")
        except Exception as e:
            print(f"WARN загрузка предыдущих данных: {e}\n")

    # Обрабатываем каждый банк
    all_signals = []
    final_banks = []

    for bank_reg in BANK_REGISTRY:
        rank = bank_reg["r"]
        existing = dict(prev_metrics.get(rank, BASE_METRICS.get(rank, {})))
        try:
            updated_metrics, bank_signals = process_bank(bank_reg, cache, existing)
        except Exception as e:
            print(f"  ERR bank {rank} {bank_reg['n']}: {e}")
            updated_metrics = existing
            bank_signals = []

        # Считаем iRoRWA
        roe = updated_metrics.get("roe")
        h20 = updated_metrics.get("h20")
        rorwa = round(roe * h20 / 100, 2) if roe and h20 else None

        bank_record = {
            "r":    bank_reg["r"],
            "n":    bank_reg["n"],
            "lo":   bank_reg["lo"],
            "lc":   bank_reg["lc"],
            "tp":   bank_reg["tp"],
            "pub":  bank_reg["pub"],
            "pf":   bank_reg["pf"],
            "frequency": bank_reg["frequency"],
            "roe":  updated_metrics.get("roe"),
            "nim":  updated_metrics.get("nim"),
            "cir":  updated_metrics.get("cir"),
            "cor":  updated_metrics.get("cor"),
            "h20":  updated_metrics.get("h20"),
            "rorwa": rorwa,
            "re":   updated_metrics.get("re", 0),
            "ne":   updated_metrics.get("ne", 0),
            "ce":   updated_metrics.get("ce", 0),
            "oe":   updated_metrics.get("oe", 0),
            "he":   updated_metrics.get("he", 0),
            "st":   bank_reg.get("status_override") or updated_metrics.get("st","nd"),
            "src":  updated_metrics.get("src","нет данных"),
        }
        final_banks.append(bank_record)
        all_signals.extend(bank_signals)
        time.sleep(1)

    # Сохраняем кэш
    save_cache(cache)

    # KPI
    kpi = compute_kpi(final_banks)

    # Финальные сигналы
    synthetic = build_synthetic_signals(final_banks)
    fresh_signals = [s for s in all_signals if s.get("priority")=="high"]
    final_signals = (fresh_signals + synthetic)[:10]

    # Статистика
    with_roe  = sum(1 for b in final_banks if b.get("roe"))
    with_pdf  = sum(1 for s in all_signals if "PDF" in s.get("text",""))

    result = {
        "updated":    TODAY,
        "updated_at": NOW,
        "kpi": kpi,
        "banks": final_banks,
        "signals": final_signals,
        "summary": (
            f"Данные обновлены {TODAY}. "
            f"Обработано банков: {len(final_banks)}, с ROE: {with_roe}/20. "
            f"Новых PDF: {with_pdf}. "
            f"Медиана ROE: {kpi['median_roe']}%. "
            f"Лидер iRoRWA: {kpi['leader_rorwa_bank']} ({kpi['leader_rorwa_val']}%)."
        ),
        "insights": [
            {"icon":"▲","text":f"Лидер iRoRWA: {kpi['leader_rorwa_bank']} — {kpi['leader_rorwa_val']}%"},
            {"icon":"⚠","text":f"Мин. буфер: {kpi['min_h20_bank']}, H20.0={kpi['min_h20_val']}%"},
            {"icon":"★","text":f"Лучший CIR в ПФ: {kpi['best_cir_pf_bank']} — {kpi['best_cir_pf_val']}%"},
            {"icon":"↓","text":"Т-Технологии: ROE 29.1% — лидер, COR 6.5% = розничная специфика"},
        ],
        "forecasts": [
            {"icon":"→","text":"Сбер 2026: ROE ~22%, NIM ~5.9%, COR <1.4%"},
            {"icon":"→","text":"ВТБ 2026: ROE 20%, восстановление NIM до 2%+"},
            {"icon":"→","text":"ДОМ.РФ 2026: прибыль >104 млрд, активы +15%"},
        ],
        "agent_stats": {
            "banks_processed": len(final_banks),
            "banks_with_roe": with_roe,
            "new_pdfs_found": with_pdf,
            "cache_size": len(cache),
        }
    }

    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")

    print(f"\n{'='*60}")
    print(f"✓ data.json обновлён")
    print(f"  Банков с ROE:    {with_roe}/20")
    print(f"  Новых сигналов:  {len(all_signals)}")
    print(f"  Кэш PDF:         {len(cache)} записей")
    print(f"  Медиана ROE:     {kpi['median_roe']}%")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
