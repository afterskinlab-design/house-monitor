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
    "KRW=X":    ("원/달러환율", "환율", "환율"),
}

# ===== 시드/적립 설정 (주문서 계산용) =====
SEED_TOTAL   = 2.0    # 시드 총액(억) — 아직 미투입분
MONTHLY      = 1000   # 월 적립(만원)
GROW_RATIO   = 0.70   # 1년차 성장블록 비중 (글라이드: 70→60→40→20)
GROW_MIX     = {"QQQM":0.50, "VOO":0.35, "SCHD":0.15}   # 성장블록 내부 배분
IMMEDIATE    = 0.50   # 성장블록 즉시 투입 비율 (나머지 8주 분할)
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


def build_orders(data):
    """현재가·환율 기반 주문서 산출"""
    fx = data.get("KRW=X",{}).get("close",1385)
    px = {tk:data.get(tk,{}).get("close",0) for tk in ["QQQM","VOO","SCHD"]}
    grow_krw = SEED_TOTAL*1e8*GROW_RATIO
    safe_krw = SEED_TOTAL*1e8*(1-GROW_RATIO)

    def shares(tk, krw):
        if px[tk]<=0 or fx<=0: return 0
        return int((krw/fx)/px[tk])

    # 시드 즉시분(성장 50%)
    seed_now = {}
    for tk,w in GROW_MIX.items():
        krw = grow_krw*w*IMMEDIATE
        seed_now[tk] = {"shares":shares(tk,krw), "krw":round(krw), "px":px[tk]}
    # 시드 분할분(성장 나머지 50%, 8주)
    seed_split = {}
    for tk,w in GROW_MIX.items():
        krw = grow_krw*w*(1-IMMEDIATE)/8
        seed_split[tk] = {"shares":shares(tk,krw), "krw":round(krw)}
    # 월적립(성장 GROW_RATIO)
    mon_grow = MONTHLY*1e4*GROW_RATIO
    monthly = {}
    for tk,w in GROW_MIX.items():
        krw = mon_grow*w
        monthly[tk] = {"shares":shares(tk,krw), "krw":round(krw)}

    return {
        "fx": round(fx,2),
        "grow_total": round(grow_krw), "safe_total": round(safe_krw),
        "seed_now": seed_now, "seed_split": seed_split,
        "monthly": monthly,
        "monthly_safe": round(MONTHLY*1e4*(1-GROW_RATIO)),
        "safe_alloc": {
            "파킹통장·CMA (원화)":round(safe_krw*0.40),
            "달러 단기채 (환노출)":round(safe_krw*0.30),
            "예금·CD (원화)":round(safe_krw*0.30)
        },
        "safe_products": {
            "파킹통장·CMA (원화)": "OK저축 읽어보는통장 / SC제일 Hi통장 / 발행어음형 CMA (한투·미래)",
            "달러 단기채 (환노출)": "TIGER 미국달러단기채권액티브 329750 — 미국금리 4~5% + 환율 노출",
            "예금·CD (원화)": "TIGER CD금리투자KIS 357870 / 저축은행 정기예금 12개월"
        },
    }

def judge(data):
    sig=[]; pct=CURRENT_ASSET/TARGET_EQUITY*100
    if CURRENT_ASSET>=TARGET_EQUITY:
        sig.append(("목표달성","danger",f"자기자본 {CURRENT_ASSET}억 도달 — 성장블록 전량 안전 전환하고 잔금까지 지키세요"))
    elif pct>=90:
        sig.append(("목표임박","warn",f"목표의 {pct:.0f}% — 성장비중 축소 고려"))
    dd=data.get("^IXIC",{}).get("drawdown",0)
    if dd<=-40: sig.append(("폭락5단계","buy",f"나스닥 {dd:.1f}% — 파킹현금까지 전량 저가매수"))
    elif dd<=-30: sig.append(("폭락4단계","buy",f"나스닥 {dd:.1f}% — 안전블록 나머지 절반 투입"))
    elif dd<=-20: sig.append(("폭락3단계","buy",f"나스닥 {dd:.1f}% — 안전블록 실탄 절반 투입"))
    elif dd<=-15: sig.append(("증액2단계","buy",f"나스닥 {dd:.1f}% — 이번달 적립 50%↑ (1,000→1,500만)"))
    elif dd<=-10: sig.append(("증액1단계","warn",f"나스닥 {dd:.1f}% — 이번달 적립 20%↑ (1,000→1,200만)"))
    elif dd<=-5: sig.append(("조정주의","warn",f"나스닥 {dd:.1f}% — 아직 정액 유지, 추가하락 감시"))

    # 나스닥 기준 성장블록 신호가 하나도 없으면 = 정상 적립
    if not sig:
        sig.append(("정상","ok","나스닥 정상권 — 성장블록 계획대로 정액 적립"))

    # 국장/위성 조정 신호 (0167A0 위성 추가매수 판단용, 성장블록과 별개)
    sat=data.get("0167A0.KS",{}).get("drawdown",0)
    if sat<=-25: sig.append(("위성폭락","buy",f"SOL반도체 {sat:.1f}% — 위성 여유분 적극 추가매수 고려"))
    elif sat<=-20: sig.append(("위성조정","warn",f"SOL반도체 {sat:.1f}% — 위성 분할 추가매수 검토"))
    elif sat<=-15: sig.append(("위성주의","info",f"SOL반도체 {sat:.1f}% — 위성 조정 관찰"))
    try:
        jd=datetime.datetime.strptime(JANDANG_DATE,"%Y-%m-%d").date()
        days=(jd-datetime.date.today()).days
        if 0<=days<=180: sig.append(("잔금임박","danger",f"잔금 D-{days}일 — 성장블록 전량 안전자산 전환"))
        elif days<0: sig.append(("잔금경과","info","잔금일 경과 — 플랜 종료"))
    except: pass
    return sig, round(pct,1)

def main():
    print(f"수집 {datetime.datetime.now():%Y-%m-%d %H:%M} UTC")
    data=fetch(); signals,pct=judge(data)
    payload={"updated":datetime.datetime.now().strftime("%Y-%m-%d %H:%M")+" (KST 새벽 자동수집)",
        "target_equity":TARGET_EQUITY,"current_asset":CURRENT_ASSET,"progress_pct":pct,
        "jandang_date":JANDANG_DATE,"prices":data,
        "orders":build_orders(data),
        "signals":[{"tag":t,"level":l,"msg":m} for t,l,m in signals]}
    json.dump(payload,open("dashboard_data.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("저장 완료 → dashboard_data.json")
    for t,l,m in signals: print(f"  [{t}] {m}")

if __name__=="__main__":
    main()
