import os, sys, json
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import update_steam as u

ROW_SALE = '''<a href="https://store.steampowered.com/app/1174180/Red_Dead_Redemption_2/?snr=1" data-ds-appid="1174180" data-ds-itemkey="App_1174180" data-ds-tagids="[1,2]" data-ds-crtrids="[1]" onmouseover="x" class="search_result_row ds_collapse_flag " data-search-page="1" data-gpnav="item">
<div class="col search_capsule"><img src="https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1174180/capsule_sm_120.jpg?t=1" srcset="a 1x"></div>
<div class="responsive_search_name_combined"><div class="col search_name ellipsis"><span class="title">Red Dead Redemption 2</span></div>
<div class="col search_released responsive_secondrow">2019년 12월 5일</div>
<div class="col search_price_discount_combined responsive_secondrow" data-price-final="1825000"><div class="discount_block search_discount_block" data-price-final="1825000" data-bundlediscount="0" data-discount="75" role="button"><div class="discount_pct">-75%</div><div class="discount_prices"><div class="discount_original_price">&#8361; 73,000</div><div class="discount_final_price">&#8361; 18,250</div></div></div></div></div></a>'''

ROW_TBD = ROW_SALE.replace("1174180", "999001").replace("Red Dead Redemption 2", "Mystery &amp; Co").replace(
    "2019년 12월 5일", "2027년 1분기").replace('data-discount="75"', 'data-discount="0"').replace(
    '<div class="discount_pct">-75%</div>', '').replace('<div class="discount_original_price">&#8361; 73,000</div>', '').replace(
    '&#8361; 18,250', '').replace('data-price-final="1825000"', 'data-price-final="0"')
ROW_BUNDLE = ROW_SALE.replace('data-ds-appid="1174180"', 'data-ds-appid="1,2,3" data-ds-bundleid="55"')
ROW_FREE = ROW_TBD.replace("999001", "999002").replace("2027년 1분기", "2026년 12월 18일").replace(
    '<div class="discount_final_price"></div>', '<div class="discount_final_price">무료 플레이</div>')


def test_dates():
    assert u.parse_release("2026년 11월 26일") == ("2026-11-26", "d", "")
    assert u.parse_release("26 Nov, 2026") == ("2026-11-26", "d", "")
    assert u.parse_release("Nov 26, 2026") == ("2026-11-26", "d", "")
    assert u.parse_release("2027년 2월") == (None, "m", "2027-02")
    assert u.parse_release("2027년 1분기") == (None, "q", "2027-Q1")
    assert u.parse_release("Q3 2027") == (None, "q", "2027-Q3")
    assert u.parse_release("2027년") == (None, "y", "2027")
    assert u.parse_release("출시 예정") == (None, "x", "")
    assert u.parse_release("추후 공개") == (None, "x", "")


def test_rows():
    rows = u.parse_search_html(ROW_SALE + ROW_TBD + ROW_BUNDLE + ROW_FREE)
    assert len(rows) == 3, rows
    a, b, c = rows
    assert a["i"] == 1174180 and a["dc"] == 75 and a["pf"] == 18250 and a["po"] == 73000 and a["d"] == "2019-12-05"
    assert b["n"] == "Mystery & Co" and b["p"] == "q" and b["dc"] == 0 and b["pf"] is None
    assert c["fr"] is True and c["pf"] == 0 and c["d"] == "2026-12-18"


def test_merge():
    KST = timezone(timedelta(hours=9))
    t0 = datetime(2026, 11, 27, 3, 0, tzinfo=KST)
    tbd = u.parse_search_html(ROW_TBD)[0]
    m1 = u.merge({}, {tbd["i"]: tbd}, set(), True, {}, t0)
    assert "dt" not in m1[999001]
    # 다음 갱신에서 날짜 확정
    dated = dict(tbd, r="2027년 3월 4일", d="2027-03-04", p="d", tk="")
    t1 = t0 + timedelta(hours=12)
    m2 = u.merge(m1, {999001: dated}, set(), True, {}, t1)
    assert m2[999001]["dt"] == t1.isoformat(timespec="minutes")
    # 출시일 연기
    later = dict(dated, d="2027-04-01")
    m3 = u.merge(m2, {999001: later}, set(), True, {}, t1 + timedelta(hours=12))
    assert m3[999001]["ch"]["f"] == "2027-03-04"
    # 할인 종료: 할인 목록이 완전히 수집됐는데 안 보이면 할인 해제
    sale = dict(u.parse_search_html(ROW_SALE)[0], d="2026-06-01")
    end = int((t0 + timedelta(days=3)).timestamp())
    s1 = u.merge({}, {sale["i"]: sale}, {sale["i"]}, True, {sale["i"]: end}, t0)
    assert s1[1174180]["se"] == end
    s2 = u.merge(s1, {}, set(), True, {}, t0 + timedelta(hours=12))
    assert s2[1174180]["dc"] == 0 and s2[1174180]["pf"] == 73000
    # 오래된 게임 정리
    assert 1174180 not in u.merge(s1, {}, set(), True, {}, datetime(2030, 1, 1, tzinfo=KST))


if __name__ == "__main__":
    test_dates(); test_rows(); test_merge()
    print("모든 테스트 통과")
