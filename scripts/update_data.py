#!/usr/bin/env python3
"""
Банковский Радар — агент ежедневного обновления.
Запускается GitHub Actions каждый день в 00:00 UTC (03:00 МСК).
"""

import json, re, sys, time, urllib.request, urllib.error, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

MSK   = timezone(timedelta(hours=3))
TODAY = datetime.now(MSK).strftime("%d.%m.%Y")
NOW   = datetime.now(MSK).strftime("%d.%m.%Y %H:%M МСК")
OUTPUT = Path(__file__).parent.parent / "data.json"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# ── БАЗОВЫЕ ДАННЫЕ (последние известные значения МСФО 2025) ─────────────
BASE = [
  {"r":1, "n":"Сбербанк",       "lo":"С","lc":"#21A038","tp":"state", "pub":1,"pf":0,
   "roe":22.7,"nim":6.2,"cir":30.3,"cor":1.3,"h20":14.6,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"data","src":"МСФО фев.2026"},
  {"r":2, "n":"ВТБ",            "lo":"В","lc":"#003087","tp":"state", "pub":1,"pf":0,
   "roe":18.3,"nim":1.4,"cir":47.3,"cor":1.1,"h20":9.8, "re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"data","src":"МСФО фев.2026"},
  {"r":3, "n":"Газпромбанк",    "lo":"Г","lc":"#1B4D9A","tp":"state", "pub":0,"pf":0,
   "roe":10.1,"nim":3.0,"cir":48.6,"cor":None,"h20":11.5,"re":0,"ne":0,"ce":0,"oe":1,"he":1,"st":"part","src":"МСФО мар.2026"},
  {"r":4, "n":"Альфа-Банк",     "lo":"А","lc":"#EF3124","tp":"private","pub":0,"pf":0,
   "roe":21.0,"nim":5.8,"cir":42.0,"cor":2.7,"h20":13.0,"re":1,"ne":1,"ce":1,"oe":1,"he":1,"st":"part","src":"МСФО апр.2026"},
  {"r":5, "n":"Россельхозбанк", "lo":"Р","lc":"#2E7D32","tp":"state", "pub":0,"pf":0,
   "roe":14.5,"nim":2.7,"cir":50.0,"cor":None,"h20":12.4,"re":0,"ne":0,"ce":0,"oe":1,"he":1,"st":"part","src":"МСФО мар.2026"},
  {"r":6, "n":"МКБ",            "lo":"М","lc":"#7B1FA2","tp":"private","pub":1,"pf":0,
   "roe":None,"nim":None,"cir":None,"cor":None,"h20":11.0,"re":0,"ne":0,"ce":0,"oe":0,"he":1,"st":"part","src":"МСФО апр.2026"},
  {"r":7, "n":"Т-Технологии",   "lo":"Т","lc":"#111111","tp":"private","pub":1,"pf":0,
   "roe":29.1,"nim":10.8,"cir":34.7,"cor":6.5,"h20":12.5,"re":0,"ne":0,"ce":0,"oe":0,"he":1,"st":"data","src":"МСФО мар.2026"},
  {"r":8, "n":"Совкомбанк",     "lo":"С","lc":"#E65100","tp":"private","pub":1,"pf":0,
   "roe":15.0,"nim":5.3,"cir":57.0,"cor":2.5,"h20":13.0,"re":0,"ne":0,"ce":0,"oe":0,"he":1,"st":"data","src":"МСФО мар.2026"},
  {"r":9, "n":"Банк ДОМ.РФ",   "lo":"Д","lc":"#1565C0","tp":"state", "pub":1,"pf":1,
   "roe":21.6,"nim":3.7,"cir":28.3,"cor":0.7,"h20":13.5,"re":0,"ne":0,"ce":0,"oe":0,"he":1,"st":"data","src":"МСФО фев.2026"},
  {"r":10,"n":"ПСБ",            "lo":"П","lc":"#AD1457","tp":"state", "pub":0,"pf":0,
   "roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"loss","src":"убыток −19.1 млрд МСФО"},
  {"r":11,"n":"Юникредит Банк", "lo":"U","lc":"#c00000","tp":"foreign","pub":0,"pf":0,
   "roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"exit","src":"уход до сер.2026"},
  {"r":12,"n":"БСПБ",           "lo":"Б","lc":"#0D47A1","tp":"private","pub":1,"pf":0,
   "roe":18.1,"nim":7.4,"cir":29.0,"cor":2.0,"h20":14.0,"re":0,"ne":1,"ce":1,"oe":1,"he":1,"st":"data","src":"МСФО мар.2026"},
  {"r":13,"n":"МТС Банк",       "lo":"М","lc":"#E53935","tp":"private","pub":1,"pf":0,
   "roe":14.5,"nim":7.2,"cir":35.7,"cor":5.5,"h20":12.0,"re":0,"ne":0,"ce":0,"oe":1,"he":1,"st":"data","src":"МСФО мар.2026"},
  {"r":14,"n":"Уралсиб",        "lo":"У","lc":"#00695C","tp":"private","pub":0,"pf":0,
   "roe":10.1,"nim":None,"cir":None,"cor":None,"h20":None,"re":1,"ne":0,"ce":0,"oe":0,"he":0,"st":"part","src":"РСБУ апр.2026"},
  {"r":15,"n":"Ак Барс",        "lo":"А","lc":"#558B2F","tp":"private","pub":0,"pf":0,
   "roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"nd","src":"нет данных"},
  {"r":16,"n":"БМ-Банк",        "lo":"О","lc":"#4527A0","tp":"state", "pub":0,"pf":0,
   "roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"nd","src":"интеграция Открытие"},
  {"r":17,"n":"Банк Россия",    "lo":"Р","lc":"#1A237E","tp":"private","pub":0,"pf":0,
   "roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"nd","src":"данные закрыты"},
  {"r":18,"n":"Промсвязьбанк",  "lo":"П","lc":"#F57F17","tp":"state", "pub":0,"pf":0,
   "roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"loss","src":"см. ПСБ"},
  {"r":19,"n":"Экспобанк",      "lo":"Э","lc":"#006064","tp":"private","pub":0,"pf":0,
   "roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"nd","src":"нет данных"},
  {"r":20,"n":"Синара Банк",    "lo":"С","lc":"#37474F","tp":"private","pub":0,"pf":0,
   "roe":None,"nim":None,"cir":None,"cor":None,"h20":None,"re":0,"ne":0,"ce":0,"oe":0,"he":0,"st":"nd","src":"нет данных"},
]

# RSS-ленты которые реально открыты без блокировки
RSS_FEEDS = [
    ("РБК Финансы",    "https://rss.rbc.ru/finances/20/02/2021/index.rss"),
    ("Коммерсантъ Банки","https://www.kommersant.ru/RSS/section-6.xml"),
    ("Интерфакс Финансы","https://www.interfax.ru/rss/financial.asp"),
]

BANK_MAP = {
    "сбер":6, "сбербанк":1, "втб":2, "газпромбанк":3,
    "альфа":4, "россельхоз":5, "рсхб":5, "мкб":6,
    "т-банк":7, "т-технологии":7, "тинькофф":7,
    "совком":8, "домрф":9, "дом.рф":9,
    "псб":10, "промсвязь":10, "бспб":12,
    "мтс банк":13, "мтс-банк":13, "уралсиб":14,
}

NUM_PATS = {
    "roe": [r'ROE\D{0,30}?([\d]+[,.][\d]+)\s*%', r'рентабельност\w+\s+капитала\D{0,20}?([\d]+[,.][\d]+)\s*%'],
    "nim": [r'NIM\D{0,30}?([\d]+[,.][\d]+)\s*%', r'процентн\w+\s+марж\w+\D{0,20}?([\d]+[,.][\d]+)\s*%'],
    "cir": [r'CIR\D{0,30}?([\d]+[,.][\d]+)\s*%', r'расходов\s+к\s+доход\w+\D{0,20}?([\d]+[,.][\d]+)\s*%'],
    "cor": [r'COR\D{0,30}?([\d]+[,.][\d]+)\s*%', r'стоимост\w+\s+риска\D{0,20}?([\d]+[,.][\d]+)\s*%'],
    "h20": [r'[НH]20\.0\D{0,20}?([\d]+[,.][\d]+)\s*%'],
}

def fetch(url, timeout=12):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language":"ru-RU,ru;q=0.9"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            enc = r.headers.get_content_charset() or "utf-8"
            return raw.decode(enc, errors="replace")
    except Exception as e:
        print(f"  WARN {url[:60]}: {e}")
        return None

def exnum(text, pats):
    for p in pats:
        m = re.search(p, text, re.I)
        if m:
            try:
                v = float(m.group(1).replace(",","."))
                return v
            except: pass
    return None

def find_rank(text):
    tl = text.lower()
    for k,r in BANK_MAP.items():
        if k in tl: return r
    return None

def parse_rss(url, source_name):
    """Парсит RSS-ленту, возвращает список сигналов и найденные обновления метрик."""
    signals, updates_map = [], {}
    html = fetch(url)
    if not html: return signals, updates_map
    try:
        root = ET.fromstring(html)
        ns = {"atom":"http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        for item in items[:30]:
            # Берём заголовок и описание
            title_el = item.find("title")
            desc_el  = item.find("description") or item.find("summary")
            title = (title_el.text or "") if title_el is not None else ""
            desc  = (desc_el.text  or "") if desc_el  is not None else ""
            text  = re.sub(r'<[^>]+>', ' ', title + " " + desc)
            text  = re.sub(r'\s+', ' ', text).strip()
            if len(text) < 30: continue
            # Ищем упоминание банка
            rank = find_rank(text)
            if not rank: continue
            bank = next((b for b in BASE if b["r"]==rank), None)
            if not bank: continue
            # Ищем метрики
            found = {}
            for metric, pats in NUM_PATS.items():
                v = exnum(text, pats)
                if v and 0.1 < v < 200:
                    found[metric] = round(v, 2)
            # Фильтруем нерелевантные
            kw = any(w in text.lower() for w in ["мсфо","roe","nim","прибыл","рентабельн","процентн","маржа","риска"])
            if not kw and not found: continue
            priority = "high" if found else ("med" if "мсфо" in text.lower() else "low")
            score    = 85 if found else (65 if "мсфо" in text.lower() else 40)
            snippet  = text[:220]
            signals.append({
                "bank":bank["n"],"logo":bank["lo"],"lc":bank["lc"],
                "type":"metric" if found else "news",
                "priority":priority,"score":score,
                "text":snippet,"tags":list(found.keys()) or ["новость"],
                "time":TODAY,
            })
            if found:
                if rank not in updates_map: updates_map[rank] = {}
                updates_map[rank].update(found)
    except Exception as e:
        print(f"  WARN parse RSS {source_name}: {e}")
    return signals, updates_map

def build_signals(banks):
    sigs = []
    wr = [b for b in banks if b.get("rorwa")]
    if wr:
        top = max(wr, key=lambda b: b["rorwa"])
        sigs.append({"bank":top["n"],"logo":top["lo"],"lc":top["lc"],
            "type":"metric","priority":"high","score":95,
            "text":f"Лидер по iRoRWA: {top['rorwa']:.2f}% (ROE {top['roe']}% × H20.0 {top['h20']}%). Наилучшая эффективность использования капитала под риском в ТОП-20.",
            "tags":["iRoRWA","лидер"],"time":TODAY})
    wh = [b for b in banks if b.get("h20")]
    if wh:
        mn = min(wh, key=lambda b: b["h20"])
        sigs.append({"bank":mn["n"],"logo":mn["lo"],"lc":mn["lc"],
            "type":"risk","priority":"high" if mn["h20"]<11 else "med","score":85,
            "text":f"Минимальный буфер капитала в секторе: H20.0 = {mn['h20']}% при регуляторном минимуме 9.25%. Буфер {round(mn['h20']-9.25,2)} пп.",
            "tags":["H20","капитал","риск"],"time":TODAY})
    pf = [b for b in banks if b.get("pf") and b.get("cir")]
    if pf:
        bc = min(pf, key=lambda b: b["cir"])
        sigs.append({"bank":bc["n"],"logo":bc["lo"],"lc":bc["lc"],
            "type":"metric","priority":"high","score":90,
            "text":f"Лучший CIR в ПФ-сегменте: {bc['cir']}% — рекордная операционная эффективность. Эскроу-модель структурно снижает стоимость риска (COR {bc.get('cor','—')}%).",
            "tags":["CIR","ПФ","эффективность"],"time":TODAY})
    for b in banks:
        if b.get("st")=="loss":
            sigs.append({"bank":b["n"],"logo":b["lo"],"lc":b["lc"],
                "type":"risk","priority":"high","score":88,
                "text":f"Убыток по МСФО: {b['src']}. Расхождение с РСБУ объясняется разными моделями оценки кредитного риска (МСФО 9 vs реактивная модель РСБУ).",
                "tags":["убыток","риск","МСФО"],"time":TODAY})
    return sigs[:8]

def compute_kpi(banks):
    roes  = [b["roe"] for b in banks if b.get("roe")]
    rorwa = [b for b in banks if b.get("rorwa")]
    pfcir = [b for b in banks if b.get("pf") and b.get("cir")]
    h20s  = [b for b in banks if b.get("h20")]
    med   = round(sorted(roes)[len(roes)//2],1) if roes else None
    ldr   = max(rorwa, key=lambda b:b["rorwa"]) if rorwa else None
    bcir  = min(pfcir, key=lambda b:b["cir"])   if pfcir else None
    mnh   = min(h20s,  key=lambda b:b["h20"])   if h20s  else None
    return {
        "median_roe":med,
        "leader_rorwa_bank": ldr["n"]    if ldr  else "—",
        "leader_rorwa_val":  ldr["rorwa"]if ldr  else None,
        "best_cir_pf_bank":  bcir["n"]  if bcir else "—",
        "best_cir_pf_val":   bcir["cir"]if bcir else None,
        "min_h20_bank":      mnh["n"]   if mnh  else "—",
        "min_h20_val":       mnh["h20"] if mnh  else None,
        "dom_rf_pf_portfolio":"1.9 трлн",
    }

def main():
    print(f"[{NOW}] Банковский Радар — агент обновления")
    banks = [dict(b) for b in BASE]

    # Загружаем предыдущий data.json — берём значения оттуда где BASE содержит None
    if OUTPUT.exists():
        try:
            prev = json.loads(OUTPUT.read_text("utf-8"))
            pm = {b["r"]:b for b in prev.get("banks",[])}
            for b in banks:
                if b["r"] in pm:
                    for f in ["roe","nim","cir","cor","h20"]:
                        if b[f] is None and pm[b["r"]].get(f) is not None:
                            b[f] = pm[b["r"]][f]
            print(f"  ✓ Загружены предыдущие данные ({prev.get('updated','?')})")
        except Exception as e:
            print(f"  WARN: {e}")

    # Парсинг RSS
    print("\n── RSS-ленты ──")
    all_signals, upd_map = [], {}
    for name, url in RSS_FEEDS:
        print(f"  {name}...")
        sigs, upds = parse_rss(url, name)
        all_signals.extend(sigs)
        for rank, vals in upds.items():
            if rank not in upd_map: upd_map[rank] = {}
            upd_map[rank].update(vals)
        print(f"    сигналов: {len(sigs)}, обновлений: {len(upds)}")
        time.sleep(1)

    # Применяем найденные обновления
    for rank, vals in upd_map.items():
        b = next((x for x in banks if x["r"]==rank), None)
        if b:
            for k,v in vals.items():
                b[k] = v
            b["src"] = f"Обновлено {TODAY}"
            print(f"  ✓ {b['n']}: {vals}")

    # Считаем iRoRWA
    for b in banks:
        b["rorwa"] = round(b["roe"]*b["h20"]/100,2) if b.get("roe") and b.get("h20") else None

    kpi = compute_kpi(banks)
    synth_sigs = build_signals(banks)
    # Приоритет синтетическим сигналам, новостные добавляем в конец
    news_sigs = [s for s in all_signals if s.get("priority")=="high"]
    final_sigs = (synth_sigs + news_sigs)[:10]

    result = {
        "updated": TODAY,
        "updated_at": NOW,
        "kpi": kpi,
        "banks": banks,
        "signals": final_sigs,
        "summary": (
            f"Данные обновлены {TODAY}. "
            f"Медиана ROE ТОП-20: {kpi['median_roe']}%. "
            f"Лидер iRoRWA: {kpi['leader_rorwa_bank']} ({kpi['leader_rorwa_val']}%). "
            f"Минимальный буфер капитала: {kpi['min_h20_bank']} "
            f"(H20.0 = {kpi['min_h20_val']}%, буфер {round((kpi['min_h20_val'] or 0)-9.25,2)} пп)."
        ),
        "insights": [
            {"icon":"▲","text":f"Лидер iRoRWA: {kpi['leader_rorwa_bank']} — {kpi['leader_rorwa_val']}% (наилучшая эффективность капитала)"},
            {"icon":"⚠","text":f"Мин. буфер капитала: {kpi['min_h20_bank']}, H20.0={kpi['min_h20_val']}% — риск при дивидендных выплатах"},
            {"icon":"★","text":f"Лучший CIR в ПФ-сегменте: {kpi['best_cir_pf_bank']} — {kpi['best_cir_pf_val']}%"},
            {"icon":"↓","text":"Т-Технологии: ROE 29.1% — лидер сектора, COR 6.5% = розничная специфика, нерелевантно для ПФ"},
        ],
        "forecasts": [
            {"icon":"→","text":"Сбер 2026: ROE ~22%, NIM ~5.9%, COR <1.4% (прогноз менеджмента)"},
            {"icon":"→","text":"ВТБ 2026: целевой ROE 20%, восстановление NIM до 2%+"},
            {"icon":"→","text":"ДОМ.РФ 2026: прибыль >104 млрд, рост активов +15% до 7.3 трлн"},
        ],
    }

    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(f"\n✓ data.json записан ({OUTPUT})")
    print(f"  Банков с ROE: {sum(1 for b in banks if b.get('roe'))}/20")
    print(f"  Сигналов: {len(final_sigs)}")
    print(f"  Медиана ROE: {kpi['median_roe']}%")

if __name__ == "__main__":
    main()
