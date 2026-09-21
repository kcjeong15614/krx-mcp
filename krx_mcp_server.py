"""
KRX Open API MCP 서버 (원격/모바일용 HTTP 버전)
- krx-openapi 패키지(https://github.com/seokhoonj/krx-openapi)를 감싸서
  Claude가 지수/주식/ETP/채권/파생/상품/ESG 일별 데이터를 조회할 수 있게 한다.
- 설치: pip install krx-openapi "fastmcp>=2.6"
- 환경변수 2개 필요:
    KRX_API_KEY   : KRX Open API 인증키
    MCP_AUTH_TOKEN: 이 MCP 서버 자체를 보호할 임의의 비밀 토큰 (직접 정해서 지정)
- 로컬 실행: python krx_mcp_server.py
- Render 등에 배포 시 PORT 환경변수를 Render가 자동으로 주입한다.
"""

import os
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from krx_openapi import KRX, catalog
from krx_openapi.exceptions import (
    KRXError,
    KRXConfigError,
    KRXAuthError,
    KRXRateLimitError,
    KRXResponseError,
    KRXNetworkError,
)

# ---------- 이 MCP 서버 자체에 대한 접근 인증 ----------
# claude.ai에서 원격 커넥터로 등록할 때, 이 토큰을 Authorization: Bearer <토큰> 으로 보내야 한다.
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN")
if not MCP_AUTH_TOKEN:
    raise RuntimeError(
        "MCP_AUTH_TOKEN 환경변수가 설정되지 않았습니다. "
        "원격 서버를 보호할 임의의 긴 비밀 문자열을 정해서 설정하세요."
    )

auth_verifier = StaticTokenVerifier(
    tokens={
        MCP_AUTH_TOKEN: {
            "client_id": "krx-mobile-client",
            "scopes": ["krx:read"],
        }
    },
    required_scopes=["krx:read"],
)

mcp = FastMCP("KRX Open API Server", auth=auth_verifier)

# KRX() 인자를 안 주면 환경변수/설정파일에서 자동으로 키를 찾는다.
krx = KRX()


def _safe_call(fn, *args, **kwargs) -> dict:
    """모든 도구가 공통으로 쓰는 에러 처리 래퍼."""
    try:
        rows = fn(*args, **kwargs)
        return {"count": len(rows), "data": rows}
    except KRXAuthError:
        return {"error": "인증 실패: 인증키가 잘못됐거나, 이 서비스에 대한 이용신청이 아직 승인되지 않았습니다."}
    except KRXRateLimitError:
        return {"error": "일일 호출 한도(10,000회)를 초과했습니다. 자정 이후 리셋됩니다."}
    except KRXConfigError:
        return {"error": "KRX_API_KEY를 찾을 수 없습니다. 환경변수나 config 파일을 확인하세요."}
    except (KRXResponseError, KRXNetworkError) as e:
        return {"error": f"조회 중 오류가 발생했습니다: {str(e)}"}
    except KRXError as e:
        return {"error": f"알 수 없는 KRX 오류: {str(e)}"}


# ---------- 지수 ----------

@mcp.tool
def get_index(group: str, date: str) -> dict:
    """
    지수 일별시세를 조회한다.

    Args:
        group: 'krx' | 'kospi' | 'kosdaq' | 'bond' | 'derivatives' 중 하나
        date: 조회일자 YYYYMMDD (예: '20260917')
    """
    methods = {
        "krx": krx.index.krx,
        "kospi": krx.index.kospi,
        "kosdaq": krx.index.kosdaq,
        "bond": krx.index.bond,
        "derivatives": krx.index.derivatives,
    }
    if group not in methods:
        return {"error": f"group은 {list(methods.keys())} 중 하나여야 합니다."}
    return _safe_call(methods[group], date)


# ---------- 주식 ----------

@mcp.tool
def get_stock_daily(date: str, market: str = "KOSPI") -> dict:
    """
    주식 일별매매정보(전종목 시세)를 조회한다.

    Args:
        date: 조회일자 YYYYMMDD
        market: 'KOSPI' | 'KOSDAQ' | 'KONEX' (기본값 KOSPI)
    """
    return _safe_call(krx.stock.daily, date, market=market)


@mcp.tool
def get_stock_info(date: str, market: str = "KOSPI") -> dict:
    """
    종목기본정보(상장일, 상장주식수, 액면가 등)를 조회한다.

    Args:
        date: 조회일자 YYYYMMDD
        market: 'KOSPI' | 'KOSDAQ' | 'KONEX' (기본값 KOSPI)
    """
    return _safe_call(krx.stock.info, date, market=market)


# ---------- ETP (ETF/ETN/ELW) ----------

@mcp.tool
def get_etp(kind: str, date: str) -> dict:
    """
    ETF/ETN/ELW 일별매매정보를 조회한다.

    Args:
        kind: 'etf' | 'etn' | 'elw' 중 하나
        date: 조회일자 YYYYMMDD
    """
    methods = {"etf": krx.etp.etf, "etn": krx.etp.etn, "elw": krx.etp.elw}
    if kind not in methods:
        return {"error": f"kind는 {list(methods.keys())} 중 하나여야 합니다."}
    return _safe_call(methods[kind], date)


# ---------- 채권 ----------

@mcp.tool
def get_bond(kind: str, date: str) -> dict:
    """
    채권 일별매매정보를 조회한다.

    Args:
        kind: 'treasury'(국채전문유통) | 'general'(일반채권) | 'small_lot'(소액채권)
        date: 조회일자 YYYYMMDD
    """
    methods = {
        "treasury": krx.bond.treasury,
        "general": krx.bond.general,
        "small_lot": krx.bond.small_lot,
    }
    if kind not in methods:
        return {"error": f"kind는 {list(methods.keys())} 중 하나여야 합니다."}
    return _safe_call(methods[kind], date)


# ---------- 파생상품 ----------

@mcp.tool
def get_derivatives(kind: str, date: str, market: str = "KOSPI") -> dict:
    """
    선물/옵션 일별매매정보를 조회한다.

    Args:
        kind: 'futures' | 'options' | 'stock_futures' | 'stock_options'
        date: 조회일자 YYYYMMDD
        market: stock_futures/stock_options에서만 사용 ('KOSPI' | 'KOSDAQ')
    """
    if kind == "futures":
        return _safe_call(krx.derivatives.futures, date)
    elif kind == "options":
        return _safe_call(krx.derivatives.options, date)
    elif kind == "stock_futures":
        return _safe_call(krx.derivatives.stock_futures, date, market=market)
    elif kind == "stock_options":
        return _safe_call(krx.derivatives.stock_options, date, market=market)
    return {"error": "kind는 futures/options/stock_futures/stock_options 중 하나여야 합니다."}


# ---------- 일반상품 ----------

@mcp.tool
def get_commodity(kind: str, date: str) -> dict:
    """
    석유/금/배출권 시장 일별매매정보를 조회한다.

    Args:
        kind: 'oil' | 'gold' | 'emissions'
        date: 조회일자 YYYYMMDD
    """
    methods = {"oil": krx.commodity.oil, "gold": krx.commodity.gold, "emissions": krx.commodity.emissions}
    if kind not in methods:
        return {"error": f"kind는 {list(methods.keys())} 중 하나여야 합니다."}
    return _safe_call(methods[kind], date)


# ---------- ESG ----------

@mcp.tool
def get_esg(kind: str, date: str) -> dict:
    """
    ESG 관련 데이터(사회책임투자채권/ESG지수/ESG증권상품)를 조회한다.

    Args:
        kind: 'sri_bond' | 'index' | 'etp'
        date: 조회일자 YYYYMMDD
    """
    methods = {"sri_bond": krx.esg.sri_bond, "index": krx.esg.index, "etp": krx.esg.etp}
    if kind not in methods:
        return {"error": f"kind는 {list(methods.keys())} 중 하나여야 합니다."}
    return _safe_call(methods[kind], date)


# ---------- 메타 정보 (키 없이도 동작) ----------

@mcp.tool
def list_services() -> dict:
    """이 서버가 지원하는 전체 그룹과 메서드 목록을 보여준다 (API 키 불필요)."""
    return {g: catalog.methods(g) for g in catalog.groups()}


@mcp.tool
def list_fields(group: str, method: str) -> dict:
    """
    특정 서비스가 반환하는 필드(컬럼)명을 보여준다 (API 키 불필요).

    Args:
        group: 예) 'index', 'stock'
        method: 예) 'kospi', 'daily'
    """
    try:
        return {"fields": catalog.fields(group, method)}
    except KeyError as e:
        return {"error": f"알 수 없는 group/method: {e}"}


if __name__ == "__main__":
    # Render는 PORT 환경변수로 바인딩할 포트를 지정해준다. 없으면 로컬 테스트용 8000.
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="http", host="0.0.0.0", port=port, path="/mcp")
