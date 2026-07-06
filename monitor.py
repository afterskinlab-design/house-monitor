#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주택자금 감시 — 매일 자동 실행 (GitHub Actions)"""
import yfinance as yf
import json, datetime, sys

# ===== 설정 (매수/납입 시 CURRENT_ASSET만 갱신) =====
TARGET_EQUITY = 8.0
CURRENT_ASSET = 2.0
JANDANG_DATE  = "2030-07-01"
WATCH = {
    "QQQM":     ("나스닥100",   "성장", "미장"),
    "VOO":      ("S&P500",     "성장", "미장"),
    "SCHD":     ("배당성장",     "성장", "미장"),
    "^IXIC":    ("나스닥지수",   "지표", "미장"),
    "069500.KS":("KODEX200",  "지표", "국장"),
    "0167A0.KS":("SOL AI반도체","위성", "국장"),
}
# ====================================================

def fetch():
    out = {}
    for tk,(name,block,mkt) in WATCH.items():
        try:
            h = yf.Ticker(tk).history(period="1y")
            if len(h)==0:
                out[tk]={"name":name,"block":block,"market":mkt,"error":"데이터 없음"}; continue
            close=float(h["Close"].iloc[-1]); prev=float(h["Close"].iloc[-2]) if len(h)>1 else close
            high1y=float(h["Close"].max())
            out[tk]={"name":name,"block":block,"market":mkt,"close":round(close,2),
                "change":round((close/prev-1)*100,2),"high_1y":round(high1y,2),
                "drawdown":round((close/high1y-1)*100,1),"date":str(h.index[-1].date())}
            print(f"  {tk:11}{name:12} {close:>12,.2f} 고점대비{(close/high1y-1)*100:+6.1f}%")
        except Exception as e:
            out[tk]={"name":name,"block":block,"market":mkt,"error":str(e)}
    return out

def judge(data):
    sig=[]; pct=CURRENT_ASSET/TARGET_EQUITY*100
    if CURRENT_ASSET>=TARGET_EQUITY:
        sig.append(("목표달성","danger",f"자기자본 {CURRENT_ASSET}억 도달 — 성장블록 전량 안전 전환하고 잔금까지 지키세요"))
    elif pct>=90:
        sig.append(("목표임박","warn",f"목표의 {pct:.0f}% — 성장비중 축소 고려"))
    dd=data.get("^IXIC",{}).get("drawdown",0)
    if dd<=-40: sig.append(("폭락4단계","buy",f"나스닥 고점대비 {dd:.1f}% — 파킹현금까지 전량 저가매수"))
    elif dd<=-30: sig.append(("폭락3단계","buy",f"나스닥 고점대비 {dd:.1f}% — 안전블록 나머지 저가매수"))
    elif dd<=-20: sig.append(("폭락2단계","buy",f"나스닥 고점대비 {dd:.1f}% — 안전블록 절반 저가매수"))
    elif dd<=-10: sig.append(("조정주의","warn",f"나스닥 고점대비 {dd:.1f}% — 사다리 대기, 추가하락 감시"))
    try:
        jd=datetime.datetime.strptime(JANDANG_DATE,"%Y-%m-%d").date()
        days=(jd-datetime.date.today()).days
        if 0<=days<=180: sig.append(("잔금임박","danger",f"잔금 D-{days}일 — 성장블록 전량 안전자산 전환"))
        elif days<0: sig.append(("잔금경과","info","잔금일 경과 — 플랜 종료"))
    except: pass
    if not sig: sig.append(("정상","ok","트리거 없음 — 계획대로 정액 적립 유지"))
    return sig, round(pct,1)

def main():
    print(f"수집 {datetime.datetime.now():%Y-%m-%d %H:%M} UTC")
    data=fetch(); signals,pct=judge(data)
    payload={"updated":datetime.datetime.now().strftime("%Y-%m-%d %H:%M")+" (KST 새벽 자동수집)",
        "target_equity":TARGET_EQUITY,"current_asset":CURRENT_ASSET,"progress_pct":pct,
        "jandang_date":JANDANG_DATE,"prices":data,
        "signals":[{"tag":t,"level":l,"msg":m} for t,l,m in signals]}
    json.dump(payload,open("dashboard_data.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("저장 완료 → dashboard_data.json")
    for t,l,m in signals: print(f"  [{t}] {m}")

if __name__=="__main__":
    main()
