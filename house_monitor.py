#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주택자금 플랜 — 하루 1회 종가 감시 스크립트
============================================
미장·국장 종가를 수집해 방어 트리거를 판정하고 dashboard_data.json으로 저장.
대시보드(house_dashboard.html)가 이 JSON을 읽어 신호등을 표시합니다.

[설치]  pip install yfinance
[실행]  python house_monitor.py
[자동화] 미장 마감 후(한국시간 아침) 하루 1회 실행 권장
         Windows: 작업 스케줄러 / Mac·Linux: crontab
         예) 매일 오전 7시:  0 7 * * *  python /경로/house_monitor.py
"""

import yfinance as yf
import json, datetime, sys

# ===== 사용자 설정 =====
TARGET_EQUITY = 8.0            # 목표 자기자본 (억)
CURRENT_ASSET = 2.0           # 현재 총자산 (억) — 매수/납입할 때마다 직접 수정
JANDANG_DATE  = "2030-07-01"  # 예상 잔금일 (D-6개월 트리거용)

# 감시 종목 (yfinance 티커)
WATCH = {
    "QQQM":     ("나스닥100",   "성장", "미장"),
    "VOO":      ("S&P500",     "성장", "미장"),
    "SCHD":     ("배당성장",     "성장", "미장"),
    "^IXIC":    ("나스닥지수",   "지표", "미장"),
    "069500.KS":("KODEX200",  "지표", "국장"),
    "0167A0.KS":("SOL AI반도체","위성", "국장"),
}
# =======================

def fetch():
    out = {}
    for tk, (name, block, mkt) in WATCH.items():
        try:
            h = yf.Ticker(tk).history(period="1y")
            if len(h) == 0:
                out[tk] = {"name": name, "block": block, "market": mkt, "error": "데이터 없음"}
                continue
            close = float(h["Close"].iloc[-1])
            prev  = float(h["Close"].iloc[-2]) if len(h) > 1 else close
            high1y= float(h["Close"].max())
            out[tk] = {
                "name": name, "block": block, "market": mkt,
                "close": round(close, 2),
                "change": round((close/prev-1)*100, 2),
                "high_1y": round(high1y, 2),
                "drawdown": round((close/high1y-1)*100, 1),
                "date": str(h.index[-1].date()),
            }
            print(f"  {tk:11} {name:12} 종가 {close:>12,.2f}  전일 {(close/prev-1)*100:+5.2f}%  고점대비 {(close/high1y-1)*100:+6.1f}%")
        except Exception as e:
            out[tk] = {"name": name, "block": block, "market": mkt, "error": str(e)}
            print(f"  {tk:11} {name:12} 에러: {e}")
    return out

def judge(data):
    signals = []

    # 트리거 1: 목표 도달 → 전량 안전 전환
    pct = CURRENT_ASSET / TARGET_EQUITY * 100
    if CURRENT_ASSET >= TARGET_EQUITY:
        signals.append(("목표달성", "danger", f"자기자본 {CURRENT_ASSET}억 도달 — 성장블록 전량 안전 전환하고 잔금까지 지키세요"))
    elif pct >= 90:
        signals.append(("목표임박", "warn", f"목표의 {pct:.0f}% — 성장비중 축소 고려"))

    # 트리거 2: 나스닥 낙폭 사다리
    nq = data.get("^IXIC", {})
    dd = nq.get("drawdown", 0)
    if dd <= -40:
        signals.append(("폭락4단계", "buy", f"나스닥 고점대비 {dd:.1f}% — 파킹현금까지 전량 저가매수"))
    elif dd <= -30:
        signals.append(("폭락3단계", "buy", f"나스닥 고점대비 {dd:.1f}% — 안전블록 나머지 저가매수"))
    elif dd <= -20:
        signals.append(("폭락2단계", "buy", f"나스닥 고점대비 {dd:.1f}% — 안전블록 절반 저가매수"))
    elif dd <= -10:
        signals.append(("조정주의", "warn", f"나스닥 고점대비 {dd:.1f}% — 사다리 대기, 추가 하락 감시"))

    # 트리거 3: 잔금 D-6개월
    try:
        jd = datetime.datetime.strptime(JANDANG_DATE, "%Y-%m-%d").date()
        days = (jd - datetime.date.today()).days
        if 0 <= days <= 180:
            signals.append(("잔금임박", "danger", f"잔금 D-{days}일 — 성장블록 전량 안전자산 전환(수익 미련 없이)"))
        elif days < 0:
            signals.append(("잔금경과", "info", "잔금일 경과 — 플랜 종료"))
    except Exception:
        pass

    if not signals:
        signals.append(("정상", "ok", "트리거 없음 — 계획대로 정액 적립 유지"))
    return signals, round(pct, 1)

def main():
    print(f"\n{'='*64}\n 주택자금 감시 — {datetime.datetime.now():%Y-%m-%d %H:%M}\n{'='*64}")
    data = fetch()
    signals, pct = judge(data)
    print(f"\n 목표 진행률: {pct}%  (현재 {CURRENT_ASSET}억 / 목표 {TARGET_EQUITY}억)")
    print(" 방어 신호:")
    for tag, level, msg in signals:
        mark = {"danger":"🔴","warn":"🟡","buy":"🔵","ok":"🟢","info":"⚪"}.get(level,"·")
        print(f"   {mark} [{tag}] {msg}")

    payload = {
        "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "target_equity": TARGET_EQUITY,
        "current_asset": CURRENT_ASSET,
        "progress_pct": pct,
        "jandang_date": JANDANG_DATE,
        "prices": data,
        "signals": [{"tag":t,"level":l,"msg":m} for t,l,m in signals],
    }
    with open("dashboard_data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n 저장 완료 → dashboard_data.json (대시보드에서 읽음)\n")

if __name__ == "__main__":
    try:
        main()
    except ImportError:
        print("yfinance 미설치. 터미널에서: pip install yfinance"); sys.exit(1)
