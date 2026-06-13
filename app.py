"""
Intelligence Dashboard - Backend v5
실행: python -m uvicorn app:app --port 8000
"""

import os, re, asyncio, logging, time, io, zipfile, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NAVER_CLIENT_ID     = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ══════════════════════════════════════════════════════════════════════════════
#  키워드 확장
# ══════════════════════════════════════════════════════════════════════════════
KEYWORD_EXPAND: dict[str, list[str]] = {
    "ESS": ["에너지저장시스템", "BESS", "배터리저장", "전력저장장치", "그리드배터리"],
    "유리기판": ["글라스코어", "glass substrate", "ABF대체", "글라스기판"],
    "2차전지": ["리튬이온배터리", "이차전지", "전기차배터리", "배터리셀"],
    "양극재": ["NCM", "NCA", "NCMA", "양극활물질", "하이니켈"],
    "2차전지 양극재": ["NCM", "NCA", "양극활물질", "하이니켈", "이차전지소재"],
    "음극재": ["흑연음극재", "실리콘음극재", "인조흑연"],
    "전해질": ["전해액", "고체전해질", "리튬염"],
    "분리막": ["배터리분리막", "separator", "습식분리막"],
    "휴머노이드": ["인간형로봇", "humanoid robot", "로봇액추에이터"],
    "휴머노이드 액추에이터": ["로봇관절", "로봇모터", "서보모터"],
    "액추에이터": ["서보모터", "구동장치", "로봇관절"],
    "리튬 가공": ["탄산리튬", "수산화리튬", "리튬정제"],
    "리튬": ["탄산리튬", "수산화리튬", "리튬원자재", "스포듀민"],
    "AI 반도체": ["NPU", "HBM", "AI칩", "뉴럴프로세서", "GPU AI"],
    "HBM": ["고대역폭메모리", "HBM3", "HBM4", "AI메모리"],
    "전고체 배터리": ["전고체전지", "solid state battery", "고체전해질배터리"],
    "도심항공모빌리티": ["UAM", "eVTOL", "플라잉카", "에어택시"],
    "핵융합 에너지": ["핵융합발전", "토카막", "ITER", "핵융합로"],
    "SiC 전력반도체": ["실리콘카바이드", "SiC MOSFET", "전력소자", "와이드밴드갭"],
    "수소": ["수소연료전지", "그린수소", "수소차", "수전해"],
    "태양광": ["솔라셀", "페로브스카이트", "태양전지", "태양광모듈"],
    "동박": ["전지박", "배터리동박", "copper foil"],
    "전구체": ["배터리전구체", "양극재전구체", "니켈전구체"],
}

# ══════════════════════════════════════════════════════════════════════════════
#  상장사 DB  (이름 → {code, desc, tags})
# ══════════════════════════════════════════════════════════════════════════════
COMPANY_INFO: dict[str, dict] = {
    # ── 반도체 / 기판 ─────────────────────────────────────────────────────────
    "삼성전자":        {"code":"005930","desc":"반도체·가전 세계 1위, HBM·AI메모리 핵심 공급사","tags":["AI 반도체","HBM","반도체","유리기판","메모리"]},
    "SK하이닉스":      {"code":"000660","desc":"HBM3E 독점 공급, AI서버 메모리 최대 수혜주","tags":["AI 반도체","HBM","반도체","메모리"]},
    "한미반도체":      {"code":"042700","desc":"HBM TC본더 글로벌 1위, AI반도체 패키징 핵심 장비","tags":["AI 반도체","HBM","반도체"]},
    "LG이노텍":        {"code":"011070","desc":"FC-BGA 기판 1위, 유리기판 개발 중","tags":["유리기판","반도체","기판"]},
    "삼성전기":        {"code":"009150","desc":"MLCC·기판 세계 상위권, 유리기판 사업 진출","tags":["유리기판","반도체","기판"]},
    "대덕전자":        {"code":"353200","desc":"HDI·패키지기판 전문, 유리기판 전환 모멘텀","tags":["유리기판","반도체","기판"]},
    "심텍":            {"code":"222800","desc":"메모리 패키지기판 전문, 유리기판 수혜 기대","tags":["유리기판","반도체","기판"]},
    "이수페타시스":    {"code":"007660","desc":"MLB 기판 전문, AI서버 기판 수요 급증 수혜","tags":["AI 반도체","HBM","기판","유리기판"]},
    "주성엔지니어링":  {"code":"036930","desc":"반도체 CVD 장비, 유리기판 증착 공정 수혜","tags":["반도체","유리기판"]},
    "원익IPS":         {"code":"240810","desc":"반도체·디스플레이 증착장비 전문","tags":["반도체","유리기판"]},
    "필옵틱스":        {"code":"161580","desc":"레이저 광학 장비, 유리기판 가공 공정 수혜","tags":["유리기판","반도체"]},
    "에스에프에이":    {"code":"056190","desc":"디스플레이·반도체 장비, 유리기판 라인 납품","tags":["유리기판","반도체"]},
    "티로보틱스":      {"code":"217330","desc":"반도체 이송 로봇, 유리기판 공정 이송 수혜","tags":["유리기판","반도체","휴머노이드"]},
    # ── 2차전지 셀 ────────────────────────────────────────────────────────────
    "LG에너지솔루션":  {"code":"373220","desc":"국내 배터리 1위, ESS·전기차 글로벌 공급","tags":["2차전지","ESS","양극재","전고체 배터리"]},
    "삼성SDI":         {"code":"006400","desc":"전기차·ESS 배터리 글로벌 3위, 전고체 선도","tags":["2차전지","ESS","전고체 배터리","양극재"]},
    "SK이노베이션":    {"code":"096770","desc":"SK온 모회사, 전기차 배터리 고성장","tags":["2차전지","ESS","양극재"]},
    # ── 양극재 / 소재 ─────────────────────────────────────────────────────────
    "에코프로비엠":    {"code":"247540","desc":"하이니켈 양극재 국내 1위, 글로벌 확장 중","tags":["양극재","2차전지","2차전지 양극재","리튬"]},
    "에코프로":        {"code":"086520","desc":"에코프로비엠 지주, 양극재 밸류체인 통합","tags":["양극재","2차전지","2차전지 양극재"]},
    "포스코퓨처엠":    {"code":"003670","desc":"양극재·음극재 수직계열화, POSCO그룹 배터리소재","tags":["양극재","음극재","2차전지","2차전지 양극재","리튬"]},
    "엘앤에프":        {"code":"066970","desc":"하이니켈 NCMA 양극재 전문, 테슬라 공급사","tags":["양극재","2차전지","2차전지 양극재"]},
    "코스모신소재":    {"code":"005070","desc":"양극재·이형필름, 전고체 소재 연구","tags":["양극재","2차전지"]},
    # ── 음극재 / 동박 ─────────────────────────────────────────────────────────
    "SKC":             {"code":"011790","desc":"동박 세계 1위(KCFT), 배터리 핵심 소재","tags":["동박","2차전지"]},
    "솔루스첨단소재":  {"code":"336370","desc":"전지박(동박) 유럽 공장 운영","tags":["동박","2차전지"]},
    "대주전자재료":    {"code":"078600","desc":"실리콘 음극재 개발, 차세대 배터리 수혜","tags":["음극재","2차전지","전고체 배터리"]},
    "한솔케미칼":      {"code":"014680","desc":"배터리 바인더·과산화수소 소재 전문","tags":["2차전지","반도체"]},
    "롯데에너지머티리얼즈":{"code":"020150","desc":"전지박(동박) 국내 최초 상업화","tags":["동박","2차전지"]},
    # ── 전해질 / 분리막 ──────────────────────────────────────────────────────
    "천보":            {"code":"278280","desc":"리튬염·전해질 첨가제 국내 1위","tags":["전해질","2차전지","리튬"]},
    "후성":            {"code":"093370","desc":"LiPF6(육불화인산리튬) 국내 유일 생산","tags":["전해질","2차전지","리튬"]},
    "솔브레인":        {"code":"357780","desc":"반도체 식각액·전해질 소재 전문","tags":["전해질","2차전지","반도체"]},
    "동화기업":        {"code":"025900","desc":"전해액 제조사, 배터리 전해질 확장","tags":["전해질","2차전지"]},
    "SK아이이테크놀로지":{"code":"361610","desc":"분리막 세계 1위, LiBS 글로벌 공급","tags":["분리막","2차전지"]},
    "더블유씨피":      {"code":"393890","desc":"습식 분리막 전문, 폴란드 공장 가동","tags":["분리막","2차전지"]},
    # ── 전구체 ───────────────────────────────────────────────────────────────
    "에코프로머티":    {"code":"450080","desc":"양극재 전구체 전문 계열사","tags":["전구체","양극재","2차전지"]},
    "고려아연":        {"code":"010130","desc":"비철금속 제련 1위, 니켈·코발트 전구체 진출","tags":["전구체","양극재","리튬"]},
    # ── ESS / 전력 ───────────────────────────────────────────────────────────
    "LS일렉트릭":      {"code":"010120","desc":"국내 최대 전력기기·ESS 시스템 공급사","tags":["ESS","수소","태양광","핵융합 에너지"]},
    "효성중공업":      {"code":"298040","desc":"중전기·ESS·수소충전소 시스템 공급","tags":["ESS","수소"]},
    "HD현대일렉트릭":  {"code":"267260","desc":"대형 변압기 글로벌 수출, AI전력망 수혜","tags":["ESS","AI 반도체"]},
    "한국전력":        {"code":"015760","desc":"국내 전력 독점, ESS 보급 정책 수혜","tags":["ESS"]},
    "LS":              {"code":"006260","desc":"LS일렉트릭 모회사, 전선·전력 인프라","tags":["ESS"]},
    "HD현대에너지솔루션":{"code":"322000","desc":"태양광 모듈·ESS 시스템 공급","tags":["태양광","ESS"]},
    # ── 수소 ────────────────────────────────────────────────────────────────
    "두산퓨얼셀":      {"code":"336260","desc":"연료전지 발전 국내 1위, 그린수소 연계","tags":["수소"]},
    "효성첨단소재":    {"code":"298050","desc":"탄소섬유 국내 1위, 수소 압력용기 소재","tags":["수소","도심항공모빌리티"]},
    "일진하이솔루스":  {"code":"271940","desc":"수소탱크 국내 1위, 수소차·버스 공급","tags":["수소"]},
    # ── 태양광 ──────────────────────────────────────────────────────────────
    "한화솔루션":      {"code":"009830","desc":"태양광 모듈 글로벌 3위, 미국 Q CELLS","tags":["태양광","ESS"]},
    "OCI홀딩스":       {"code":"010060","desc":"폴리실리콘 생산, 태양광 핵심 소재","tags":["태양광"]},
    # ── 로봇 / 휴머노이드 ────────────────────────────────────────────────────
    "레인보우로보틱스":{"code":"277810","desc":"이족보행 로봇 국내 선두, 삼성전자 투자","tags":["휴머노이드","액추에이터","휴머노이드 액추에이터"]},
    "두산로보틱스":    {"code":"454910","desc":"협동로봇 국내 1위, 산업용 자동화 확장","tags":["휴머노이드","액추에이터"]},
    "에스피지":        {"code":"058610","desc":"감속기 전문, 로봇·자동화 핵심 부품","tags":["휴머노이드","액추에이터","휴머노이드 액추에이터"]},
    "삼익THK":         {"code":"004490","desc":"볼스크류·리니어가이드, 로봇 구동 핵심","tags":["휴머노이드","액추에이터","휴머노이드 액추에이터"]},
    "에스비비테크":    {"code":"389500","desc":"하모닉 감속기 국내 유일, 로봇 관절 핵심","tags":["휴머노이드","액추에이터","휴머노이드 액추에이터"]},
    "유진로봇":        {"code":"056080","desc":"서비스로봇·자율주행 청소로봇 전문","tags":["휴머노이드"]},
    "로보티즈":        {"code":"108490","desc":"스마트 액추에이터 전문, 로봇 관절 모듈","tags":["휴머노이드","액추에이터","휴머노이드 액추에이터"]},
    "현대위아":        {"code":"011210","desc":"공작기계·로봇 모듈, 현대차그룹 부품","tags":["휴머노이드","액추에이터"]},
    "HD현대로보틱스":  {"code":"267270","desc":"산업용 로봇 국내 1위, 자동화솔루션","tags":["휴머노이드","액추에이터"]},
    # ── 항공우주 / SpaceX 관련 ───────────────────────────────────────────────
    "한화에어로스페이스":{"code":"012450","desc":"항공엔진·우주발사체 추진계, 방산 1위, 누리호 참여","tags":["도심항공모빌리티","우주","스페이스엑스","항공우주"]},
    "KAI":             {"code":"047810","desc":"국내 유일 완성항공기 제조, 누리호 조립·우주발사체","tags":["도심항공모빌리티","우주","스페이스엑스","항공우주"]},
    "AP위성":          {"code":"211270","desc":"위성 통신단말기 전문, 저궤도위성(LEO) 직접 수혜","tags":["우주","스페이스엑스","위성","항공우주"]},
    "쎄트렉아이":      {"code":"099440","desc":"위성 본체 설계·제조 국내 1위, 수출형 소형위성","tags":["우주","스페이스엑스","위성","항공우주"]},
    "인텔리안테크":    {"code":"189300","desc":"위성 안테나 글로벌 1위, 스타링크 대응 안테나 공급","tags":["우주","스페이스엑스","위성","항공우주"]},
    "LIG넥스원":       {"code":"079550","desc":"정밀유도무기·위성항법 전문, 우주방산 수혜","tags":["우주","스페이스엑스","항공우주"]},
    "컨텍":            {"code":"451280","desc":"지상국 안테나·위성데이터 수신 전문 스타트업","tags":["우주","스페이스엑스","위성"]},
    "빅텍":            {"code":"065450","desc":"군용 전원장치·위성부품 공급, 우주방산 수혜","tags":["우주","스페이스엑스","항공우주"]},
    "한국항공우주":    {"code":"047810","desc":"KAI — 한국형발사체·위성 조립 국내 독점","tags":["우주","스페이스엑스","항공우주"]},
    "미래에셋증권":    {"code":"006800","desc":"스페이스X·미국 우주주 ETF 운용, 우주 테마 펀드 선두","tags":["우주","스페이스엑스","항공우주","위성"]},
    "한화투자증권":    {"code":"003530","desc":"우주·방산 관련 ETF·펀드 운용사","tags":["우주","스페이스엑스","항공우주"]},
    "이노스페이스":    {"code":"462350","desc":"소형 액체로켓 개발·발사체 스타트업 코스닥 상장","tags":["우주","스페이스엑스","항공우주"]},
    "나라스페이스테크":{"code":"490650","desc":"초소형 위성 제조·우주데이터 서비스","tags":["우주","스페이스엑스","위성"]},
    "한양이엔지":      {"code":"045450","desc":"우주발사체 지상설비·특수산업 설비 공급","tags":["우주","스페이스엑스","항공우주"]},
    "켄코아에어로스페이스":{"code":"274090","desc":"항공기 구조부품 제조, 우주·방산 복합소재","tags":["우주","항공우주","도심항공모빌리티"]},
    "에이치제이중공업":{"code":"097270","desc":"방산·우주 구조물 제조, 누리호 하단부 제작 참여","tags":["우주","항공우주","스페이스엑스"]},
    # ── 소재 / 화학 ──────────────────────────────────────────────────────────
    "POSCO홀딩스":     {"code":"005490","desc":"철강·리튬·양극재 수직계열화","tags":["리튬","양극재","2차전지","리튬 가공"]},
    "LG화학":          {"code":"051910","desc":"양극재·배터리소재·석유화학 사업","tags":["양극재","2차전지","전해질"]},
    # ── 자동차 ──────────────────────────────────────────────────────────────
    "현대자동차":      {"code":"005380","desc":"전기차·수소차 글로벌 3위, UAM·로봇 투자","tags":["2차전지","수소","도심항공모빌리티","휴머노이드"]},
    "기아":            {"code":"000270","desc":"전기차 EV6·EV9 글로벌 확장","tags":["2차전지","ESS"]},
    "현대모비스":      {"code":"012330","desc":"전동화 부품·자율주행 모듈 핵심 공급","tags":["2차전지","휴머노이드"]},
    # ── 리튬 / 광물 ──────────────────────────────────────────────────────────
    "광진윈텍":        {"code":"044060","desc":"리튬 가공·이차전지 소재 유통","tags":["리튬","리튬 가공","2차전지"]},
}

# ══════════════════════════════════════════════════════════════════════════════
#  키워드 → 테마 종목 직접 매핑  (기사 언급 여부 무관하게 무조건 표시)
# ══════════════════════════════════════════════════════════════════════════════
KEYWORD_COMPANIES: dict[str, list[str]] = {
    "스페이스엑스":   ["한화에어로스페이스","KAI","AP위성","쎄트렉아이","인텔리안테크","LIG넥스원","컨텍","빅텍","미래에셋증권","이노스페이스","나라스페이스테크","한양이엔지","켄코아에어로스페이스","에이치제이중공업"],
    "우주":           ["한화에어로스페이스","KAI","AP위성","쎄트렉아이","인텔리안테크","LIG넥스원","컨텍","빅텍","이노스페이스","나라스페이스테크","미래에셋증권"],
    "항공우주":       ["한화에어로스페이스","KAI","LIG넥스원","켄코아에어로스페이스","에이치제이중공업","미래에셋증권"],
    "위성":           ["AP위성","쎄트렉아이","인텔리안테크","컨텍","나라스페이스테크","LIG넥스원"],
    "ESS":            ["LG에너지솔루션","삼성SDI","LS일렉트릭","효성중공업","HD현대일렉트릭","한국전력","LS","한화솔루션"],
    "2차전지":        ["LG에너지솔루션","삼성SDI","SK이노베이션","에코프로비엠","포스코퓨처엠","엘앤에프","에코프로","SKC"],
    "양극재":         ["에코프로비엠","에코프로","포스코퓨처엠","엘앤에프","코스모신소재","LG화학"],
    "2차전지 양극재": ["에코프로비엠","에코프로","포스코퓨처엠","엘앤에프","코스모신소재","에코프로머티"],
    "음극재":         ["포스코퓨처엠","대주전자재료","솔루스첨단소재","SKC"],
    "동박":           ["SKC","솔루스첨단소재","롯데에너지머티리얼즈"],
    "분리막":         ["SK아이이테크놀로지","더블유씨피"],
    "전해질":         ["천보","후성","솔브레인","동화기업"],
    "전구체":         ["에코프로머티","고려아연","포스코퓨처엠"],
    "유리기판":       ["삼성전기","LG이노텍","대덕전자","심텍","이수페타시스","필옵틱스","에스에프에이","주성엔지니어링"],
    "AI 반도체":      ["삼성전자","SK하이닉스","한미반도체","이수페타시스","HD현대일렉트릭"],
    "HBM":            ["SK하이닉스","삼성전자","한미반도체","이수페타시스"],
    "휴머노이드":     ["레인보우로보틱스","두산로보틱스","에스피지","삼익THK","에스비비테크","로보티즈","HD현대로보틱스","현대위아"],
    "휴머노이드 액추에이터":["레인보우로보틱스","에스피지","삼익THK","에스비비테크","로보티즈","두산로보틱스"],
    "액추에이터":     ["에스피지","삼익THK","에스비비테크","로보티즈","현대위아"],
    "리튬":           ["POSCO홀딩스","고려아연","에코프로비엠","포스코퓨처엠","광진윈텍","천보","후성"],
    "리튬 가공":      ["POSCO홀딩스","고려아연","광진윈텍"],
    "도심항공모빌리티":["한화에어로스페이스","KAI","현대자동차","효성첨단소재","켄코아에어로스페이스"],
    "수소":           ["두산퓨얼셀","효성중공업","효성첨단소재","일진하이솔루스","현대자동차"],
    "태양광":         ["한화솔루션","OCI홀딩스","HD현대에너지솔루션","LS일렉트릭"],
    "핵융합 에너지":  ["LS일렉트릭","HD현대일렉트릭","효성중공업"],
    "전고체 배터리":  ["삼성SDI","LG에너지솔루션","대주전자재료","코스모신소재"],
    "SiC 전력반도체": ["HD현대일렉트릭","효성중공업","LS일렉트릭"],
}

# ══════════════════════════════════════════════════════════════════════════════
#  유틸
# ══════════════════════════════════════════════════════════════════════════════
def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    for e, c in [("&quot;",'"'),("&amp;","&"),("&#39;","'"),("&lt;","<"),("&gt;",">"),("&nbsp;"," ")]:
        text = text.replace(e, c)
    return " ".join(text.split())

def domain_of(url: str) -> str:
    try: return urlparse(url).netloc.replace("www.", "")
    except: return ""

def parse_dt(s: str) -> datetime:
    s = (s or "").strip()
    for fmt in ["%a, %d %b %Y %H:%M:%S %z","%a, %d %b %Y %H:%M:%S GMT",
                "%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%SZ"]:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except: pass
    if re.match(r"^\d{8}$", s):
        try: return datetime(int(s[:4]),int(s[4:6]),int(s[6:]),tzinfo=timezone.utc)
        except: pass
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", s)
    if m:
        try: return datetime(int(m.group(1)),int(m.group(2)),int(m.group(3)),tzinfo=timezone.utc)
        except: pass
    return datetime(1970,1,1,tzinfo=timezone.utc)

def fmt_date(s: str) -> str:
    dt = parse_dt(s)
    return "" if dt.year == 1970 else dt.strftime("%Y.%m.%d")

def is_english(text: str) -> bool:
    if not text: return False
    alpha = re.findall(r'[a-zA-Z]', text)
    return len(alpha) / max(len(text),1) > 0.55

def make_item(title, link, desc, source, pub_raw, itype):
    return {
        "title":   (title or "").strip(),
        "link":    (link  or "").strip(),
        "description": (desc or "").strip(),
        "source":  (source or "").strip(),
        "pubDate": fmt_date(pub_raw),
        "_dt":     parse_dt(pub_raw).timestamp(),
        "type":    itype,
    }

def dedup(items: list, limit=50) -> list:
    seen_url, seen_title, out = set(), set(), []
    for it in items:
        # URL 중복: 쿼리파라미터 제거 후 비교
        url_key = re.sub(r'[?#&].*$', '', it.get("link", "")).rstrip("/")
        # 제목 중복: 공백·특수문자 제거 후 앞 30자
        title_key = re.sub(r'[\s\W]', '', it.get("title", "")).lower()[:30]
        if url_key and url_key in seen_url: continue
        if title_key and title_key in seen_title: continue
        if url_key: seen_url.add(url_key)
        if title_key: seen_title.add(title_key)
        out.append(it)
        if len(out) >= limit: break
    return out

def score_relevance(item: dict, query: str, expanded_terms: list[str]) -> int:
    title = item.get("title", "").lower()
    desc  = item.get("description", "").lower()
    q     = query.lower()
    score = 0
    # 제목에 주요 키워드 포함 → 고점
    if q in title:
        score += 10
    elif all(w in title for w in q.split() if len(w) > 1):
        score += 6
    # 설명에 주요 키워드 포함
    if q in desc:
        score += 3
    # 확장 키워드 보너스
    for term in expanded_terms:
        t = term.lower()
        if t in title: score += 2
        if t in desc:  score += 1
    return score

def sort_by_date(items: list) -> list:
    return sorted(items, key=lambda x: x.get("_dt",0), reverse=True)

def expand_query(query: str) -> str:
    extras = []
    for k, v in KEYWORD_EXPAND.items():
        if k in query or query in k:
            extras.extend(v[:3])
    if extras:
        terms = " OR ".join(f'"{t}"' if " " in t else t for t in extras[:5])
        return f"{query} OR {terms}"
    return query

# ── 번역 (Google Translate 무료 엔드포인트) ─────────────────────────────────
async def translate_ko(text: str, client: httpx.AsyncClient) -> str:
    if not text or not is_english(text): return text
    try:
        r = await client.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client":"gtx","sl":"auto","tl":"ko","dt":"t","q":text},
            timeout=5.0,
        )
        data = r.json()
        return "".join(p[0] for p in data[0] if p[0]).strip()
    except:
        return text

# ── 관련 상장사 집계 ─────────────────────────────────────────────────────────
def extract_companies_from_all(items: list, query: str) -> list:
    # 1) 키워드 테마 직접 매핑 (기사 언급 여부 무관)
    theme_names: list[str] = []
    for kw, names in KEYWORD_COMPANIES.items():
        if kw in query or query in kw:
            for n in names:
                if n not in theme_names:
                    theme_names.append(n)

    # 2) 기사 본문 언급 집계 (보완)
    mentions: dict[str, int] = {}
    for item in items:
        text = f"{item.get('title','')} {item.get('description','')}"
        for name in COMPANY_INFO:
            if name in text:
                mentions[name] = mentions.get(name, 0) + 1

    # 3) 테마 종목 우선 + 기사 언급 종목 추가
    ordered: list[str] = list(theme_names)
    for name, _ in sorted(mentions.items(), key=lambda x: -x[1]):
        if name not in ordered:
            ordered.append(name)

    results = []
    for name in ordered:
        info = COMPANY_INFO.get(name)
        if not info or not info.get("code"): continue
        is_theme   = name in theme_names
        mention_cnt = mentions.get(name, 0)
        results.append({
            "name":     name,
            "code":     info["code"],
            "url":      f"https://finance.naver.com/item/main.naver?code={info['code']}",
            "desc":     info["desc"],
            "is_theme": is_theme,
            "mentions": mention_cnt,
        })

    return results  # 개수 제한 없음

# ══════════════════════════════════════════════════════════════════════════════
#  NEWS
# ══════════════════════════════════════════════════════════════════════════════
async def news_google_rss(query: str, client: httpx.AsyncClient, limit=60) -> list:
    expanded = expand_query(query)
    url = f"https://news.google.com/rss/search?q={quote(expanded)}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        r = await client.get(url, headers=HEADERS, timeout=12.0)
        root  = ET.fromstring(r.content)
        items = root.findall(".//item")[:limit]
        logger.info(f"Google news RSS: {len(items)}")
    except Exception as e:
        logger.warning(f"Google news RSS: {e}"); return []

    results = []
    for it in items:
        title  = clean(it.findtext("title",""))
        link   = (it.findtext("link") or "").strip()
        desc   = clean(it.findtext("description",""))
        pub    = it.findtext("pubDate","")
        src_el = it.find("source")
        source = src_el.text if src_el is not None and src_el.text else domain_of(link)
        results.append(make_item(title, link, desc, source, pub, "news"))

    # 영문 제목 번역
    trans_tasks = [translate_ko(it["title"], client) for it in results]
    translated  = await asyncio.gather(*trans_tasks, return_exceptions=True)
    for item, t in zip(results, translated):
        if isinstance(t, str) and t: item["title"] = t
    return results

async def news_naver_api(query: str, client: httpx.AsyncClient) -> list:
    if not NAVER_CLIENT_ID: return []
    try:
        r = await client.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers={"X-Naver-Client-Id":NAVER_CLIENT_ID,"X-Naver-Client-Secret":NAVER_CLIENT_SECRET},
            params={"query":query,"display":20,"sort":"date"},
            timeout=10.0,
        )
        items = r.json().get("items",[])
    except Exception as e:
        logger.warning(f"Naver news API: {e}"); return []
    return [make_item(clean(it.get("title","")),
                      it.get("originallink") or it.get("link",""),
                      clean(it.get("description","")),
                      domain_of(it.get("originallink","")),
                      it.get("pubDate",""), "news") for it in items]

async def news_daum(query: str, client: httpx.AsyncClient) -> list:
    url = f"https://search.daum.net/search?w=news&q={quote(query)}&sort=recency"
    try:
        r = await client.get(url, headers=HEADERS, timeout=10.0, follow_redirects=True)
        soup = BeautifulSoup(r.content, "html.parser")
    except Exception as e:
        logger.warning(f"Daum: {e}"); return []
    results, cards = [], []
    for sel in ["li.item-list","div.news_area","div.coll_cont"]:
        cards = soup.select(sel)
        if cards: break
    for card in cards[:20]:
        a = card.select_one("a.tit_main") or card.select_one("a.tit_g") or card.select_one("a[class*='tit']")
        if not a: continue
        title = clean(a.get_text()); link = a.get("href","")
        if link.startswith("//"): link = "https:" + link
        if not link.startswith("http"): continue
        desc = clean((card.select_one("p.desc") or card.select_one("a.desc") or BeautifulSoup("","html.parser")).get_text())
        src  = clean((card.select_one("span.medium_tit") or BeautifulSoup("","html.parser")).get_text()) or domain_of(link)
        pub  = clean((card.select_one("span.date") or BeautifulSoup("","html.parser")).get_text())
        if title and link: results.append(make_item(title,link,desc,src,pub,"news"))
    return results

# ══════════════════════════════════════════════════════════════════════════════
#  BLOG
# ══════════════════════════════════════════════════════════════════════════════
async def blog_naver_api(query: str, client: httpx.AsyncClient) -> list:
    if not NAVER_CLIENT_ID: return []
    try:
        r = await client.get(
            "https://openapi.naver.com/v1/search/blog.json",
            headers={"X-Naver-Client-Id":NAVER_CLIENT_ID,"X-Naver-Client-Secret":NAVER_CLIENT_SECRET},
            params={"query":query,"display":20,"sort":"date"},
            timeout=10.0,
        )
        items = r.json().get("items",[])
    except Exception as e:
        logger.warning(f"Naver blog API: {e}"); return []
    return [make_item(clean(it.get("title","")), it.get("link",""),
                      clean(it.get("description","")),
                      it.get("bloggername",""), it.get("postdate",""), "blog") for it in items]

async def blog_google_rss(query: str, client: httpx.AsyncClient, limit=60) -> list:
    expanded = expand_query(query)
    site_q   = f"({expanded}) (site:tistory.com OR site:blog.naver.com OR site:brunch.co.kr OR site:velog.io)"
    url = f"https://news.google.com/rss/search?q={quote(site_q)}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        r = await client.get(url, headers=HEADERS, timeout=12.0)
        root  = ET.fromstring(r.content)
        items = root.findall(".//item")[:limit]
        logger.info(f"Google blog RSS: {len(items)}")
    except Exception as e:
        logger.warning(f"Google blog RSS: {e}"); return []

    results = []
    for it in items:
        title  = clean(it.findtext("title",""))
        link   = (it.findtext("link") or "").strip()
        desc   = clean(it.findtext("description",""))
        pub    = it.findtext("pubDate","")
        source = domain_of(link)
        results.append(make_item(title,link,desc,source,pub,"blog"))

    trans_tasks = [translate_ko(it["title"], client) for it in results]
    translated  = await asyncio.gather(*trans_tasks, return_exceptions=True)
    for item, t in zip(results, translated):
        if isinstance(t, str) and t: item["title"] = t
    return results

async def blog_naver_scrape(query: str, client: httpx.AsyncClient) -> list:
    url = f"https://search.naver.com/search.naver?where=blog&query={quote(query)}&sm=tab_opt&nso=so%3Add"
    try:
        r = await client.get(url, headers=HEADERS, timeout=12.0, follow_redirects=True)
        soup = BeautifulSoup(r.content, "html.parser")
    except Exception as e:
        logger.warning(f"Naver blog scrape: {e}"); return []
    results, cards = [], []
    for sel in ["li.bx","div.total_area","div.blog_area"]:
        cards = soup.select(sel)
        if cards: break
    for card in cards[:20]:
        a = (card.select_one("a.title_link") or card.select_one("a.api_txt_lines") or
             card.select_one("a[class*='title']"))
        if not a: continue
        title = clean(a.get_text()); link = a.get("href","")
        if not link.startswith("http"): continue
        desc_tag = card.select_one("div.dsc_wrap") or card.select_one("a.dsc_txt_wrap")
        desc = clean(desc_tag.get_text()) if desc_tag else ""
        src_tag = card.select_one("a.sub_txt.sub_name") or card.select_one("span.sub_name")
        source = clean(src_tag.get_text()) if src_tag else "네이버블로그"
        pub = ""
        for span in card.select("span"):
            t = span.get_text(strip=True)
            if re.search(r"\d{4}[.\-]\d{2}[.\-]\d{2}",t): pub=t; break
        results.append(make_item(title,link,desc,source,pub,"blog"))
    return results

# ══════════════════════════════════════════════════════════════════════════════
#  파이프라인
# ══════════════════════════════════════════════════════════════════════════════
def filter_by_relevance(items: list, query: str, min_score: int = 3) -> list:
    expanded = KEYWORD_EXPAND.get(query, [])
    scored = [(score_relevance(it, query, expanded), it) for it in items]
    # 점수 0이어도 날짜가 있고 키워드가 한 글자짜리면 통과 (단어 검색 예외)
    if len(query) <= 2:
        min_score = 0
    return [it for sc, it in scored if sc >= min_score]

async def pipeline_news(query: str) -> list:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        g,n,d = await asyncio.gather(news_google_rss(query,client),
                                      news_naver_api(query,client),
                                      news_daum(query,client))
    all_items = sort_by_date(g+n+d)
    relevant  = filter_by_relevance(all_items, query)
    return dedup(relevant, limit=50)

async def pipeline_blog(query: str) -> list:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        na,gb,ns = await asyncio.gather(blog_naver_api(query,client),
                                         blog_google_rss(query,client),
                                         blog_naver_scrape(query,client))
    all_items = sort_by_date(na+gb+ns)
    relevant  = filter_by_relevance(all_items, query, min_score=2)
    return dedup(relevant, limit=50)

# ══════════════════════════════════════════════════════════════════════════════
#  DART 전자공시 API
# ══════════════════════════════════════════════════════════════════════════════
DART_API_KEY = os.getenv("DART_API_KEY", "")

ACCT_MAP: dict[str, list[str]] = {
    "revenue":                ["매출액","영업수익","수익(매출액)","매출"],
    "cogs":                   ["매출원가","영업비용"],
    "gross_profit":           ["매출총이익","매출총손익"],
    "sga":                    ["판매비와관리비","판매비및일반관리비"],
    "operating_profit":       ["영업이익","영업손익"],
    "pretax_profit":          ["법인세비용차감전순이익","법인세차감전순이익","법인세비용차감전계속사업이익"],
    "tax":                    ["법인세비용"],
    "net_profit":             ["당기순이익","당기순손익"],
    "total_assets":           ["자산총계"],
    "current_assets":         ["유동자산"],
    "non_current_assets":     ["비유동자산"],
    "tangible_assets":        ["유형자산"],
    "intangible_assets":      ["무형자산"],
    "total_liabilities":      ["부채총계"],
    "current_liabilities":    ["유동부채"],
    "non_current_liabilities":["비유동부채"],
    "equity":                 ["자본총계"],
    "depreciation":           ["유형자산상각비","감가상각비","상각비"],
}

def _pnum(s) -> int | None:
    try: return int(str(s).replace(",","").strip())
    except: return None

def _find_acct(items: list, key: str, field: str = "thstrm_amount") -> int | None:
    for pat in ACCT_MAP.get(key, []):
        for it in items:
            if pat in it.get("account_nm",""):
                return _pnum(it.get(field,""))
    return None

def _build_row(items: list, field: str = "thstrm_amount") -> dict:
    row = {k: _find_acct(items, k, field) for k in ACCT_MAP}
    op, dep = row.get("operating_profit"), row.get("depreciation")
    row["ebitda"] = (op or 0) + (dep or 0) if op is not None else None
    return row

def _fmt_won(v: int | None) -> str:
    if v is None: return "-"
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1_000_000_000_000: return f"{sign}{a/1_000_000_000_000:.2f}조"
    if a >= 100_000_000:       return f"{sign}{a/100_000_000:,.0f}억"
    if a >= 10_000:            return f"{sign}{a/10_000:,.0f}만"
    return f"{sign}{a:,}"

def _fmtd(s: str) -> str:
    s = (s or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}.{s[4:6]}.{s[6:]}"
    return s or "-"

# DART 기업코드 사전 매핑 (corp_name → (corp_code, stock_code))
# corpCode.xml에서 사전 추출 — Vercel 타임아웃 방지
DART_CORP_MAP: dict[str, tuple[str,str]] = {
    "AP위성":           ("00874803","211270"),
    "HD현대에너지솔루션": ("01199550","322000"),
    "HD현대로보틱스":    ("00164795","267270"),
    "HD현대일렉트릭":    ("01205851","267260"),
    "KAI":             ("00309503","047810"),
    "LG에너지솔루션":    ("01515323","373220"),
    "LIG넥스원":        ("00214120","079550"),
    "LG이노텍":         ("00105961","011070"),
    "LG화학":           ("00356361","051910"),
    "LS":              ("00105952","006260"),
    "LS일렉트릭":       ("00109519","010120"),
    "OCI홀딩스":        ("00148896","010060"),
    "POSCO홀딩스":      ("00155319","005490"),
    "SKC":             ("00139889","011790"),
    "SK아이이테크놀로지": ("01386916","361610"),
    "SK이노베이션":      ("00631518","096770"),
    "SK하이닉스":       ("00164779","000660"),
    "고려아연":          ("00102858","010130"),
    "광진윈텍":          ("00261928","044060"),
    "기아":             ("00106641","000270"),
    "나라스페이스테크":   ("01810832","490650"),
    "대덕전자":          ("01478712","353200"),
    "대주전자재료":       ("00177816","078600"),
    "더블유씨피":        ("01291317","393890"),
    "동화기업":          ("00570633","025900"),
    "두산로보틱스":      ("01105153","454910"),
    "두산퓨얼셀":        ("01412725","336260"),
    "레인보우로보틱스":   ("01261644","277810"),
    "로보티즈":          ("00946030","108490"),
    "롯데에너지머티리얼즈":("00113997","020150"),
    "미래에셋증권":      ("00111722","006800"),
    "빅텍":             ("00385363","065450"),
    "삼성SDI":          ("00126362","006400"),
    "삼성전기":          ("00126371","009150"),
    "삼성전자":          ("00126380","005930"),
    "삼익THK":          ("00127802","004380"),
    "솔루스첨단소재":    ("01412822","336370"),
    "솔브레인":          ("01489648","357780"),
    "심텍":             ("01095722","222800"),
    "쎄트렉아이":        ("00449254","099320"),
    "에스비비테크":      ("00567897","389500"),
    "에스에프에이":      ("00358271","056190"),
    "에스피지":          ("00220686","058610"),
    "에코프로":          ("00536541","086520"),
    "에코프로머티":      ("01311408","450080"),
    "에코프로비엠":      ("01160363","247540"),
    "에이치제이중공업":   ("00202597","097270"),
    "엘앤에프":          ("00398701","066970"),
    "원익IPS":          ("01135941","240810"),
    "유진로봇":          ("00234227","056080"),
    "이노스페이스":      ("01700587","462350"),
    "이수페타시스":      ("00107613","007660"),
    "인텔리안테크":      ("00664181","189300"),
    "일진하이솔루스":    ("00972503","271940"),
    "주성엔지니어링":    ("00252135","036930"),
    "천보":             ("00897752","278280"),
    "컨텍":             ("01685251","451760"),
    "켄코아에어로스페이스":("01158553","274090"),
    "코스모신소재":      ("00129989","005070"),
    "티로보틱스":        ("00867098","117730"),
    "포스코퓨처엠":      ("00155276","003670"),
    "필옵틱스":          ("00938721","161580"),
    "한국전력":          ("00113194","015760"),
    "한국항공우주":      ("00309503","047810"),
    "한미반도체":        ("00161383","042700"),
    "한솔케미칼":        ("00140955","014680"),
    "한양이엔지":        ("00216762","045100"),
    "한화솔루션":        ("00162461","009830"),
    "한화에어로스페이스": ("00126566","012450"),
    "한화투자증권":      ("00148610","003530"),
    "현대모비스":        ("00164788","012330"),
    "현대위아":          ("00106623","011210"),
    "현대자동차":        ("00164742","005380"),
    "효성중공업":        ("01316245","298040"),
    "효성첨단소재":      ("01316251","298050"),
    "후성":             ("00595191","093370"),
}

async def _dart_search(name: str, client) -> tuple[str,str]:
    if not DART_API_KEY: return "",""
    # 1. 사전 매핑 정확 매칭
    if name in DART_CORP_MAP:
        return DART_CORP_MAP[name]
    # 2. 사전 매핑 부분 매칭
    matches = [(k,v) for k,v in DART_CORP_MAP.items() if name in k or k in name]
    if matches:
        matches.sort(key=lambda x: len(x[0]))
        return matches[0][1]
    return "",""

async def _dart_info(corp_code: str, client) -> dict:
    if not DART_API_KEY or not corp_code: return {}
    try:
        r = await client.get("https://opendart.fss.or.kr/api/company.json",
            params={"crtfc_key":DART_API_KEY,"corp_code":corp_code}, timeout=8.0)
        d = r.json()
        if d.get("status") != "000": return {}
        cls_map = {"Y":"유가증권(KOSPI)","K":"코스닥(KOSDAQ)","N":"코넥스","E":"기타"}
        return {
            "corp_name":    d.get("corp_name",""),
            "corp_name_eng":d.get("corp_name_eng",""),
            "ceo_nm":       d.get("ceo_nm",""),
            "est_dt":       _fmtd(d.get("est_dt","")),
            "listing_dt":   _fmtd(d.get("listing_dt","")),
            "stock_code":   (d.get("stock_code","") or "").strip(),
            "corp_cls":     cls_map.get(d.get("corp_cls",""),""),
            "adres":        d.get("adres",""),
            "phn_no":       d.get("phn_no",""),
            "hm_url":       d.get("hm_url",""),
            "acc_mt":       d.get("acc_mt",""),
        }
    except Exception as e: logger.warning(f"DART info: {e}"); return {}

async def _dart_fs(corp_code: str, year: int, reprt: str, client) -> list:
    if not DART_API_KEY or not corp_code: return []
    for fs_div in ["CFS","OFS"]:
        try:
            r = await client.get("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
                params={"crtfc_key":DART_API_KEY,"corp_code":corp_code,
                        "bsns_year":str(year),"reprt_code":reprt,"fs_div":fs_div},
                timeout=12.0)
            d = r.json()
            if d.get("status") == "000" and d.get("list"): return d["list"]
        except Exception as e: logger.warning(f"DART fs {year} {reprt} {fs_div}: {e}")
    return []

async def _dart_holders(corp_code: str, year: int, client) -> list:
    if not DART_API_KEY or not corp_code: return []
    try:
        r = await client.get("https://opendart.fss.or.kr/api/hyslrSttus.json",
            params={"crtfc_key":DART_API_KEY,"corp_code":corp_code,
                    "bsns_year":str(year),"reprt_code":"11011"}, timeout=8.0)
        d = r.json()
        if d.get("status") != "000": return []
        return [{"name":s.get("nm",""),"relation":s.get("relate",""),
                 "shares":s.get("stock_co",""),"ratio":s.get("posesn_stock_co","")}
                for s in d.get("list",[])]
    except Exception as e: logger.warning(f"DART holders: {e}"); return []

async def _naver_coinfo(code: str, client) -> dict:
    """네이버 증권 coinfo 페이지 한 번에 스크래핑 (기업개요·시총·주식수·외국인비율)"""
    result = {"overview": "", "products": [], "segments": [],
              "market_cap": "", "issued_shares": "", "foreign_ratio": ""}
    if not code: return result
    hdrs = {**HEADERS, "Referer": "https://finance.naver.com/"}
    try:
        r = await client.get(
            f"https://finance.naver.com/item/coinfo.naver?code={code}&target=company",
            headers=hdrs, timeout=12.0)
        soup = BeautifulSoup(r.content, "html.parser", from_encoding="euc-kr")

        # ── 기업개요 ──────────────────────────────────────────────────
        summary_div = soup.find("div", id="summary_info") or soup.select_one("div.summary_info")
        if summary_div:
            paras = [re.sub(r'\s+', ' ', p.get_text()).strip()
                     for p in summary_div.find_all("p") if p.get_text(strip=True)]
            overview = " ".join(paras)
            overview = re.sub(r'출처\s*:\s*\S+.*$', '', overview).strip()
            result["overview"] = overview[:700]

        # ── 시가총액·상장주식수·외국인비율 ────────────────────────────
        # th.find_next_sibling('td') 로 정확하게 매핑
        for th in soup.find_all("th"):
            key = th.get_text(strip=True)
            td  = th.find_next_sibling("td")
            if not td: continue
            val = re.sub(r'\s+', ' ', td.get_text()).strip()

            if key == "시가총액":
                # "1,885조 4,249억원" 형태로 정리
                result["market_cap"] = re.sub(r'\s+', '', val).replace("원", "원")

            elif key == "상장주식수":
                shares_clean = val.replace(",", "")
                if shares_clean.isdigit():
                    n = int(shares_clean)
                    if n >= 100_000_000:
                        result["issued_shares"] = f"{n/100_000_000:.2f}억주"
                    elif n >= 10_000:
                        result["issued_shares"] = f"{n/10_000:.0f}만주"
                    else:
                        result["issued_shares"] = f"{n:,}주"

            elif "외국인소진율" in key or "외국인지분율" in key:
                result["foreign_ratio"] = val  # 이미 "47.58%" 형태

    except Exception as e: logger.warning(f"Naver coinfo: {e}")
    return result

async def _naver_shareholders_scrape(code: str, client) -> list:
    """네이버 증권 주요주주 스크래핑 (상장사)"""
    if not code: return []
    hdrs = {**HEADERS, "Referer": "https://finance.naver.com/"}
    try:
        r = await client.get(
            f"https://finance.naver.com/item/coinfo.naver?code={code}&target=stock",
            headers=hdrs, timeout=10.0)
        soup = BeautifulSoup(r.content, "html.parser", from_encoding="euc-kr")
        for tbl in soup.find_all("table"):
            ths = [th.get_text(strip=True) for th in tbl.find_all("th")]
            if any(k in " ".join(ths) for k in ["주주","주식수","지분","보유"]):
                rows = []
                for row in tbl.find_all("tr")[1:]:
                    tds = [re.sub(r'\s+',' ',td.get_text()).strip() for td in row.find_all("td")]
                    if len(tds) >= 3 and tds[0]:
                        rows.append({
                            "name":     tds[0],
                            "relation": tds[1] if len(tds) > 1 else "-",
                            "shares":   tds[2] if len(tds) > 2 else "-",
                            "ratio":    tds[3].replace("%","") if len(tds) > 3 else "-",
                        })
                if rows: return rows[:10]
    except Exception as e: logger.warning(f"Naver shareholders: {e}")
    return []

# _naver_biz_info / _naver_stock_detail → _naver_coinfo 로 통합
async def _naver_biz_info(code: str, client) -> dict:
    d = await _naver_coinfo(code, client)
    return {"overview": d["overview"], "products": d["products"], "segments": d["segments"]}

async def _naver_stock_detail(code: str, client) -> dict:
    d = await _naver_coinfo(code, client)
    return {"market_cap": d["market_cap"],
            "issued_shares": d["issued_shares"],
            "foreign_ratio": d["foreign_ratio"]}

async def _naver_metrics(code: str, client) -> dict:
    if not code: return {}
    result = {}
    try:
        r = await client.get(f"https://m.stock.naver.com/api/stock/{code}/basic",
            headers=HEADERS, timeout=5.0)
        d = r.json()
        price = d.get("closePrice","").replace(",","")
        diff  = d.get("compareToPreviousClosePrice","")
        ratio = d.get("fluctuationsRatio","")
        sign  = "+" if diff and not diff.startswith("-") else ""
        result.update({
            "price":  f"{int(price):,}원" if price.lstrip("-").isdigit() else "-",
            "diff":   f"{sign}{diff}원" if diff else "-",
            "ratio":  f"{sign}{ratio}%" if ratio else "-",
            "up":     not (diff or "").startswith("-"),
            "market": d.get("marketType",""),
        })
    except Exception as e: logger.warning(f"Naver basic: {e}")
    try:
        r2 = await client.get(f"https://m.stock.naver.com/api/stock/{code}/invest",
            headers=HEADERS, timeout=5.0)
        d2 = r2.json()
        for info in d2.get("totalInfos",[]):
            k = info.get("code","").upper()
            if k in {"PER","PBR","EPS","BPS","ROE","ROA","DIV","DPS"}:
                result[k] = f"{info.get('value','-')}{info.get('unit','')}"
    except Exception as e: logger.warning(f"Naver invest: {e}")
    return result

# ══════════════════════════════════════════════════════════════════════════════
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
async def root(): return FileResponse("index.html")

@app.get("/api/search")
async def search(q: str = Query(..., min_length=1)):
    logger.info(f"=== Search: '{q}' ===")
    news, blog = await asyncio.gather(pipeline_news(q), pipeline_blog(q))
    companies  = extract_companies_from_all(news + blog, q)
    for item in news + blog: item.pop("_dt", None)
    return JSONResponse({
        "query": q, "news": news, "blog": blog,
        "total": len(news)+len(blog),
        "companies": companies,
        "using_api": bool(NAVER_CLIENT_ID),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

@app.get("/api/stocks")
async def get_stocks(codes: str = Query(...)):
    """종목코드 콤마 구분 → 실시간 주가 일괄 조회"""
    code_list = [c.strip() for c in codes.split(",") if c.strip()][:30]
    async with httpx.AsyncClient() as client:
        async def fetch_one(code: str):
            try:
                r = await client.get(
                    f"https://m.stock.naver.com/api/stock/{code}/basic",
                    headers=HEADERS, timeout=5.0,
                )
                d = r.json()
                price = d.get("closePrice","").replace(",","")
                diff  = d.get("compareToPreviousClosePrice","")
                ratio = d.get("fluctuationsRatio","")
                sign  = "+" if not diff.startswith("-") else ""
                return code, {
                    "price": f"{int(price):,}" if price.lstrip("-").isdigit() else price,
                    "diff":  f"{sign}{diff}",
                    "ratio": f"{sign}{ratio}%",
                    "up":    not diff.startswith("-"),
                }
            except:
                return code, None
        results = await asyncio.gather(*[fetch_one(c) for c in code_list])
    return JSONResponse({code: data for code, data in results if data})

@app.get("/api/company")
async def get_company(q: str = Query(..., min_length=1)):
    logger.info(f"=== Company: '{q}' ===")
    cur = datetime.now().year
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # DART 코드 검색
        corp_code, dart_sc = await _dart_search(q, client)
        # 종목코드: DART → COMPANY_INFO 순으로 확보
        stock_code = dart_sc
        if not stock_code:
            for n, info in COMPANY_INFO.items():
                if q == n or (len(q) > 1 and q in n):
                    stock_code = info.get("code",""); break

        # 연간(5개년) 분기(최근 5분기) 재무 + 기본정보 + 주주 + 주가 병렬 조회
        annual_years = [cur-1-i for i in range(5)]
        q_specs = [(cur-1,"11014"),(cur-1,"11013"),(cur-1,"11012"),
                   (cur-2,"11014"),(cur-2,"11013")]
        q_labels = [f"{y}/{'3Q' if r=='11014' else '2Q' if r=='11013' else '1Q'}"
                    for y,r in q_specs]

        results = await asyncio.gather(
            _dart_info(corp_code, client),
            _dart_holders(corp_code, cur-1, client),
            _naver_metrics(stock_code, client),
            _naver_coinfo(stock_code, client),          # 기업개요+시총+주식수+외국인
            _naver_shareholders_scrape(stock_code, client),
            *[_dart_fs(corp_code, y, "11011", client) for y in annual_years],
            *[_dart_fs(corp_code, y, r,       client) for y,r in q_specs],
            return_exceptions=True,
        )

        corp_info       = results[0] if isinstance(results[0], dict) else {}
        dart_holders    = results[1] if isinstance(results[1], list) else []
        stock_data      = results[2] if isinstance(results[2], dict) else {}
        naver_ci        = results[3] if isinstance(results[3], dict) else {}
        naver_holders   = results[4] if isinstance(results[4], list) else []
        # 상장사면 네이버 주주 우선, 없으면 DART fallback
        holders = naver_holders if naver_holders else dart_holders
        # 네이버 코인포에서 시가총액·주식수·외국인비율 보완
        stock_data["market_cap"]    = naver_ci.get("market_cap","")
        stock_data["issued_shares"] = naver_ci.get("issued_shares","")
        stock_data["foreign_ratio"] = naver_ci.get("foreign_ratio","")
        # 사업정보
        biz_info = {"overview": naver_ci.get("overview",""),
                    "products": naver_ci.get("products",[]),
                    "segments": naver_ci.get("segments",[])}
        raw_ann = results[5:5+len(annual_years)]
        raw_qtr = results[5+len(annual_years):]

        # 연간 재무 파싱
        annual_fs = []
        for items, year in zip(raw_ann, annual_years):
            if isinstance(items, list) and items:
                row = _build_row(items)
                annual_fs.append({"period":str(year), **{k:_fmt_won(v) for k,v in row.items()}})

        # 분기 재무 파싱
        quarter_fs = []
        for items, label in zip(raw_qtr, q_labels):
            if isinstance(items, list) and items:
                row = _build_row(items)
                quarter_fs.append({"period":label, **{k:_fmt_won(v) for k,v in row.items()}})

        # COMPANY_INFO 설명 보완
        desc_from_db = ""
        for n, info in COMPANY_INFO.items():
            if q == n or (corp_info.get("corp_name") and corp_info["corp_name"] == n):
                desc_from_db = info.get("desc",""); break

        return JSONResponse({
            "query":       q,
            "has_dart":    bool(corp_code and DART_API_KEY),
            "corp_code":   corp_code,
            "corp_info":   corp_info,
            "desc":        desc_from_db,
            "stock_code":  stock_code,
            "stock_data":  stock_data,
            "annual_fs":   annual_fs,
            "quarter_fs":  quarter_fs,
            "shareholders":holders,
            "biz_info":    biz_info,
        })

@app.get("/api/health")
async def health():
    return {"status":"ok","naver_api":bool(NAVER_CLIENT_ID)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
