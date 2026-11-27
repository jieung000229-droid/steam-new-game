#!/usr/bin/env python3
"""
스팀 게임 달력 데이터 갱신 스크립트
- 출시 예정 / 최근 출시 / 할인 중 게임을 Steam 상점 검색에서 모아
  site/data/games.json 으로 저장합니다.
- 날짜가 확정되지 않은 게임(분기·연도·미정)은 따로 표시하고,
  다음 갱신 때 날짜가 확정되면 '최근 확정'으로 표시합니다.
- 추가 설치 없이 파이썬 기본 기능만 사용합니다.

GitHub Actions 가 매일 한국시간 03:00, 15:00 에 자동으로 실행합니다.
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

# ───────────── 설정 (필요하면 숫자만 바꾸세요) ─────────────
MAX_COMING_SOON = 20000   # 출시 예정 게임 최대 개수
MAX_RECENT = 3000         # 최근 출시된 게임 최대 개수
MAX_SPECIALS = 10000      # 할인 중 게임 최대 개수
KEEP_PAST_DAYS = 730      # 출시된 지 이 일수가 지난 게임은 목록에서 정리
DROP_UNSEEN_DAYS = 45     # 출시 전 게임이 이 기간 동안 안 보이면 정리(삭제·비공개 추정)
PAGE_SIZE = 100
SLEEP = 1.0               # 요청 사이 쉬는 시간(초) - Steam 차단 방지
# ────────────────────────────────────────────────────────

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "data", "games.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
SEARCH = "https://store.steampowered.com/search/results/"
GETITEMS = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
FEATURED = "https://store.steampowered.com/api/featuredcategories"
IMG_PREFIX = "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/"


def log(*a):
    print(*a, flush=True)


def http_get(url, retries=5):
    wait = 5
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept-Language": "ko-KR,ko;q=0.9",
                "Cookie": "birthtime=0; lastagecheckage=1-0-1990; wants_mature_content=1",
            })
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            log(f"  HTTP {e.code} (시도 {attempt + 1}/{retries})")
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except Exception as e:  # 네트워크 오류
            log(f"  오류: {e} (시도 {attempt + 1}/{retries})")
        time.sleep(wait)
        wait = min(wait * 2, 90)
    raise RuntimeError("요청 실패: " + url[:120])


# ───────────── 날짜 해석 ─────────────
EN_MON = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_release(text):
    """출시일 글자 → (YYYY-MM-DD 또는 None, 정밀도, 미확정 정렬키)
    정밀도: d=날짜 확정, m=월만, q=분기, y=연도, x=미정"""
    t = (text or "").strip()
    m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", t)
    if m:
        return _ymd(m.group(1), m.group(2), m.group(3))
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})", t)  # 26 Nov, 2026
    if m and m.group(2).lower()[:3] in EN_MON:
        return _ymd(m.group(3), EN_MON[m.group(2).lower()[:3]], m.group(1))
    m = re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", t)  # Nov 26, 2026
    if m and m.group(1).lower()[:3] in EN_MON:
        return _ymd(m.group(3), EN_MON[m.group(1).lower()[:3]], m.group(2))
    m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월", t)
    if m:
        return None, "m", f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"([A-Za-z]{3})[a-z]*\s+(\d{4})", t)
    if m and m.group(1).lower()[:3] in EN_MON:
        return None, "m", f"{m.group(2)}-{EN_MON[m.group(1).lower()[:3]]:02d}"
    m = re.search(r"(\d{4})\s*년\s*([1-4])\s*분기", t) or re.search(r"Q([1-4])\s*(\d{4})", t)
    if m:
        a, b = m.group(1), m.group(2)
        y, q = (a, b) if len(a) == 4 else (b, a)
        return None, "q", f"{y}-Q{q}"
    m = re.search(r"(20\d{2}|19\d{2})", t)
    if m:
        return None, "y", m.group(1)
    return None, "x", ""


def _ymd(y, mo, d):
    try:
        return date(int(y), int(mo), int(d)).isoformat(), "d", ""
    except ValueError:
        return None, "x", ""


# ───────────── 검색 결과 해석 ─────────────
ROW_RE = re.compile(r"<a\s([^>]*?search_result_row[^>]*)>(.*?)</a>", re.S)


def _attr(tag, name):
    m = re.search(r'\b' + re.escape(name) + r'="([^"]*)"', tag)
    return m.group(1) if m else None


def _won(text):
    """'₩ 16,500' → 16500, '무료'/'Free' → 0, 없으면 None"""
    if text is None:
        return None
    t = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
    if not t:
        return None
    if "무료" in t or "free" in t.lower():
        return 0
    digits = re.sub(r"[^\d]", "", t)
    return int(digits) if digits else None


def parse_search_html(results_html):
    games = []
    for m in ROW_RE.finditer(results_html or ""):
        tag, body = m.group(1), m.group(2)
        appid = _attr(tag, "data-ds-appid")
        if not appid or not appid.isdigit():   # 번들·패키지 제외
            continue
        if _attr(tag, "data-ds-bundleid") or _attr(tag, "data-ds-packageid"):
            continue
        tm = re.search(r'<span class="title">(.*?)</span>', body, re.S)
        name = html.unescape(tm.group(1)).strip() if tm else f"App {appid}"
        rm = re.search(r'class="[^"]*search_released[^"]*">(.*?)</div>', body, re.S)
        rel = html.unescape(re.sub(r"<[^>]+>", "", rm.group(1))).strip() if rm else ""
        im = re.search(r'<img[^>]+src="([^"]+)"', body)
        img = im.group(1) if im else ""

        disc = 0
        dm = re.search(r'data-discount="(\d+)"', body)
        if dm:
            disc = int(dm.group(1))
        else:
            pm = re.search(r'class="discount_pct">\s*-?(\d+)%', body)
            disc = int(pm.group(1)) if pm else 0
        final = orig = None
        fm = re.search(r'class="discount_final_price[^"]*">(.*?)</div>', body, re.S)
        om = re.search(r'class="discount_original_price">(.*?)</div>', body, re.S)
        if fm:
            final = _won(fm.group(1))
        if om:
            orig = _won(om.group(1))
        if final is None:
            pf = re.search(r'data-price-final="(\d+)"', body)
            if pf and int(pf.group(1)) > 0:
                final = int(pf.group(1)) // 100
        if orig is None:
            orig = final
        free = final == 0 and fm is not None

        d, p, tk = parse_release(rel)
        games.append({
            "i": int(appid), "n": name, "r": rel, "d": d, "p": p, "tk": tk,
            "img": img, "pf": final, "po": orig, "dc": disc, "fr": free,
        })
    return games


def crawl(label, extra, limit):
    found, start, total = {}, 0, None
    complete = False
    while start < limit:
        params = {"query": "", "start": start, "count": PAGE_SIZE, "category1": 998,
                  "cc": "kr", "l": "koreana", "infinite": 1, "ignore_preferences": 1}
        params.update(extra)
        url = SEARCH + "?" + urllib.parse.urlencode(params)
        try:
            data = json.loads(http_get(url))
        except Exception as e:
            log(f"[{label}] {start}번째에서 중단: {e}")
            break
        total = int(data.get("total_count") or 0)
        rows = parse_search_html(data.get("results_html", ""))
        if not rows:
            complete = True
            break
        new = 0
        for g in rows:
            if g["i"] not in found:
                found[g["i"]] = g
                new += 1
        start += PAGE_SIZE
        log(f"[{label}] {min(start, total)}/{total}  (+{new})")
        if start >= total:
            complete = True
            break
        if new == 0:
            complete = True
            break
        time.sleep(SLEEP)
    return found, complete


# ───────────── 할인 종료일 ─────────────
def fetch_sale_ends(appids):
    """Steam 상점 API에서 할인 종료 시각(유닉스 시간)을 가져옵니다."""
    ends = {}
    ids = list(appids)
    for k in range(0, len(ids), 50):
        chunk = ids[k:k + 50]
        body = {"ids": [{"appid": a} for a in chunk],
                "context": {"language": "koreana", "country_code": "KR"},
                "data_request": {"include_all_purchase_options": True}}
        url = GETITEMS + "?" + urllib.parse.urlencode({"input_json": json.dumps(body)})
        try:
            data = json.loads(http_get(url, retries=3))
        except Exception as e:
            log(f"  할인 종료일 일부 실패: {e}")
            continue
        for it in (data.get("response") or {}).get("store_items", []):
            opts = []
            if it.get("best_purchase_option"):
                opts.append(it["best_purchase_option"])
            opts += it.get("purchase_options") or []
            best = None
            for o in opts:
                for ad in o.get("active_discounts") or []:
                    e = int(ad.get("discount_end_date") or 0)
                    if e and (best is None or e > best):
                        best = e
            if best:
                ends[int(it.get("appid") or it.get("id") or 0)] = best
        log(f"  할인 종료일 {min(k + 50, len(ids))}/{len(ids)}")
        time.sleep(SLEEP)
    return ends


def fetch_featured_ends():
    ends = {}
    try:
        data = json.loads(http_get(FEATURED + "?cc=kr&l=koreana", retries=3))
        for it in (data.get("specials") or {}).get("items", []):
            if it.get("discount_expiration"):
                ends[int(it["id"])] = int(it["discount_expiration"])
    except Exception as e:
        log(f"  추천 할인 목록 실패: {e}")
    return ends


# ───────────── 이전 데이터와 합치기 ─────────────
def load_old():
    try:
        with open(OUT, encoding="utf-8") as f:
            return {g["i"]: g for g in json.load(f).get("games", [])}
    except Exception:
        return {}


def short_img(appid, url):
    p = f"{IMG_PREFIX}{appid}/"
    return url[len(p):] if url.startswith(p) else url


def merge(old, fresh, specials_ids, specials_complete, sale_ends, now):
    today = now.date().isoformat()
    now_s = now.isoformat(timespec="minutes")
    now_ts = int(now.timestamp())
    out = {}

    for gid, g in fresh.items():
        prev = old.get(gid, {})
        g = dict(g)
        g["img"] = short_img(gid, g.get("img", ""))
        g["fs"] = prev.get("fs", today)
        g["u"] = now_s
        # 미확정 → 확정 감지
        if prev and prev.get("p") != "d" and g["p"] == "d":
            g["dt"] = now_s
        elif prev.get("dt"):
            g["dt"] = prev["dt"]
        # 출시일 변경(연기·당김) 감지
        if prev.get("p") == "d" and g["p"] == "d" and prev.get("d") != g["d"]:
            g["ch"] = {"f": prev.get("d"), "a": now_s}
        elif prev.get("ch") and prev["ch"].get("f") != g.get("d"):
            g["ch"] = prev["ch"]
        # 할인
        if g.get("dc"):
            e = sale_ends.get(gid) or (prev.get("se") if prev.get("dc") else None)
            g["se"] = e if e and e > now_ts else None
        else:
            g["se"] = None
        out[gid] = g

    # 이번에 안 보인 기존 게임
    for gid, g in old.items():
        if gid in out:
            continue
        g = dict(g)
        if g.get("dc"):
            ended = (g.get("se") and g["se"] <= now_ts) or (specials_complete and gid not in specials_ids)
            if ended:
                g["dc"], g["pf"], g["se"] = 0, g.get("po", g.get("pf")), None
        # 출시일 지난 게임은 상태만 바뀜(날짜로 자동 계산). 오래된 것 정리
        if g.get("p") == "d" and g.get("d"):
            if g["d"] < (now.date() - timedelta(days=KEEP_PAST_DAYS)).isoformat():
                continue
            if g["d"] > today and _days_since(g.get("u"), now) > DROP_UNSEEN_DAYS:
                continue
        elif _days_since(g.get("u"), now) > DROP_UNSEEN_DAYS:
            continue
        out[gid] = g
    return out


def _days_since(iso, now):
    try:
        return (now - datetime.fromisoformat(iso)).days
    except Exception:
        return 0


def compact(g):
    keep = {k: v for k, v in g.items() if v not in (None, "", False, 0) or k in ("i", "dc")}
    if keep.get("po") == keep.get("pf"):
        keep.pop("po", None)
    if not keep.get("dc"):
        keep.pop("dc", None)
    return keep


def main():
    now = datetime.now(KST)
    log(f"갱신 시작: {now:%Y-%m-%d %H:%M} (한국시간)")
    old = load_old()
    log(f"기존 데이터: {len(old)}개")

    coming, c_ok = crawl("출시 예정", {"filter": "comingsoon"}, MAX_COMING_SOON)
    recent, r_ok = crawl("최근 출시", {"sort_by": "Released_DESC"}, MAX_RECENT)
    specials, s_ok = crawl("할인 중", {"specials": 1}, MAX_SPECIALS)

    if not (coming or recent or specials):
        log("Steam에서 아무것도 받지 못했습니다. 기존 데이터를 그대로 둡니다.")
        sys.exit(1)

    fresh = {}
    for src in (recent, coming, specials):   # 할인 정보가 가장 나중에 덮어씀
        for gid, g in src.items():
            if gid in fresh:
                base = fresh[gid]
                if g.get("dc"):
                    base.update({k: g[k] for k in ("pf", "po", "dc", "fr")})
                if not base.get("r") and g.get("r"):
                    base.update({k: g[k] for k in ("r", "d", "p", "tk")})
            else:
                fresh[gid] = g

    on_sale = [gid for gid, g in fresh.items() if g.get("dc")]
    log(f"할인 종료일 확인: {len(on_sale)}개")
    ends = fetch_featured_ends()
    ends.update(fetch_sale_ends(on_sale))

    merged = merge(old, fresh, set(specials), s_ok, ends, now)
    games = sorted((compact(g) for g in merged.values()), key=lambda g: (g.get("d") or "9999", g["n"]))

    stat = {
        "total": len(games),
        "dated": sum(1 for g in games if g.get("p") == "d"),
        "tbd": sum(1 for g in games if g.get("p") != "d"),
        "on_sale": sum(1 for g in games if g.get("dc")),
        "sale_with_end": sum(1 for g in games if g.get("se")),
    }
    meta = {
        "updated_at": now.isoformat(timespec="minutes"),
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),
        "img_prefix": IMG_PREFIX,
        "complete": {"coming": c_ok, "recent": r_ok, "specials": s_ok},
        "stat": stat,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "games": games}, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT)
    with open(os.path.join(os.path.dirname(OUT), "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    log(f"완료: {stat}")


if __name__ == "__main__":
    main()
