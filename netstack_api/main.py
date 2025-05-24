"""
NetStack API - Open5GS + UERANSIM 雙 Slice 管理 API

基於 Hexagonal Architecture 的 FastAPI 應用程式，
提供 5G 核心網 UE 管理和 Slice 切換功能。
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List

import structlog
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CollectorRegistry
from prometheus_client.exposition import generate_latest
from fastapi import Response

from .adapters.mongo_adapter import MongoAdapter
from .adapters.redis_adapter import RedisAdapter
from .adapters.open5gs_adapter import Open5GSAdapter
from .services.ue_service import UEService
from .services.slice_service import SliceService, SliceType
from .services.health_service import HealthService
from .models.requests import SliceSwitchRequest
from .models.responses import (
    HealthResponse,
    UEInfoResponse,
    UEStatsResponse,
    SliceSwitchResponse,
    ErrorResponse,
)

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

# Prometheus 指標
# 使用自定義 Registry 而非默認的全局 Registry
from prometheus_client import Counter, Histogram, CollectorRegistry

# 建立自定義 Registry
prometheus_registry = CollectorRegistry()

# 在自定義 Registry 中註冊指標
REQUEST_COUNT = Counter(
    "netstack_api_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status"],
    registry=prometheus_registry,
)

REQUEST_DURATION = Histogram(
    "netstack_api_request_duration_seconds",
    "Time spent processing API requests",
    ["method", "endpoint"],
    registry=prometheus_registry,
)

SLICE_SWITCH_COUNT = Counter(
    "netstack_slice_switch_total",
    "Total number of slice switches",
    ["from_slice", "to_slice", "status"],
    registry=prometheus_registry,
)

UE_ATTACH_COUNT = Counter(
    "netstack_ue_attach_total",
    "Total number of UE attachments",
    ["slice_type", "status"],
    registry=prometheus_registry,
)

RTT_HISTOGRAM = Histogram(
    "netstack_slice_rtt_seconds",
    "RTT latency by slice type",
    ["slice_type"],
    registry=prometheus_registry,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    logger.info("🚀 NetStack API 啟動中...")

    # 初始化適配器
    mongo_adapter = MongoAdapter(
        connection_string=os.getenv("DATABASE_URL", "mongodb://mongo:27017/open5gs")
    )
    redis_adapter = RedisAdapter(
        connection_string=os.getenv("REDIS_URL", "redis://redis:6379")
    )
    open5gs_adapter = Open5GSAdapter(mongo_host=os.getenv("MONGO_HOST", "mongo"))

    # 初始化服務
    ue_service = UEService(mongo_adapter, redis_adapter)
    slice_service = SliceService(mongo_adapter, open5gs_adapter)
    health_service = HealthService(mongo_adapter, redis_adapter)

    # 儲存到應用程式狀態
    app.state.mongo_adapter = mongo_adapter
    app.state.redis_adapter = redis_adapter
    app.state.open5gs_adapter = open5gs_adapter
    app.state.ue_service = ue_service
    app.state.slice_service = slice_service
    app.state.health_service = health_service

    # 連接外部服務
    await mongo_adapter.connect()
    await redis_adapter.connect()

    logger.info("✅ NetStack API 啟動完成")

    yield

    # 清理資源
    logger.info("🛑 NetStack API 關閉中...")
    await mongo_adapter.disconnect()
    await redis_adapter.disconnect()
    logger.info("✅ NetStack API 已關閉")


# 建立 FastAPI 應用程式
app = FastAPI(
    title="NetStack API",
    description="Open5GS + UERANSIM 雙 Slice 核心網管理 API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生產環境應限制具體域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request, call_next):
    """請求指標中介軟體"""
    method = request.method
    endpoint = request.url.path

    with REQUEST_DURATION.labels(method=method, endpoint=endpoint).time():
        response = await call_next(request)

    REQUEST_COUNT.labels(
        method=method, endpoint=endpoint, status=response.status_code
    ).inc()

    return response


# ===== 健康檢查端點 =====


@app.get("/health", response_model=HealthResponse, tags=["健康檢查"])
async def health_check():
    """
    檢查 NetStack 系統健康狀態

    回傳各核心服務的健康狀態，包括：
    - MongoDB 連線狀態
    - Redis 連線狀態
    - Open5GS 核心網服務狀態
    """
    try:
        health_service = app.state.health_service
        health_status = await health_service.check_system_health()

        if health_status["overall_status"] == "healthy":
            return HealthResponse(**health_status)
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=health_status
            )
    except Exception as e:
        logger.error("健康檢查失敗", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "健康檢查失敗", "message": str(e)},
        )


@app.get("/metrics", tags=["監控"])
async def get_metrics():
    """
    Prometheus 指標端點

    回傳系統運行指標，供 Prometheus 收集
    """
    return Response(
        content=generate_latest(prometheus_registry), media_type="text/plain"
    )


# ===== UE 管理端點 =====


@app.get("/api/v1/ue/{imsi}", response_model=UEInfoResponse, tags=["UE 管理"])
async def get_ue_info(imsi: str):
    """
    取得指定 IMSI 的 UE 資訊

    Args:
        imsi: UE 的 IMSI 號碼 (例如: 999700000000001)

    Returns:
        UE 的詳細資訊，包括目前 Slice、APN 設定等
    """
    try:
        ue_service = app.state.ue_service
        ue_info = await ue_service.get_ue_info(imsi)

        if not ue_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"找不到 IMSI {imsi} 的 UE",
            )

        return UEInfoResponse(**ue_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("取得 UE 資訊失敗", imsi=imsi, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "取得 UE 資訊失敗", "message": str(e)},
        )


@app.get("/api/v1/ue/{imsi}/stats", response_model=UEStatsResponse, tags=["UE 管理"])
async def get_ue_stats(imsi: str):
    """
    取得指定 UE 的統計資訊

    Args:
        imsi: UE 的 IMSI 號碼

    Returns:
        UE 的統計資訊，包括連線時間、流量統計、RTT 等
    """
    try:
        ue_service = app.state.ue_service
        stats = await ue_service.get_ue_stats(imsi)

        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"找不到 IMSI {imsi} 的統計資料",
            )

        return UEStatsResponse(**stats)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("取得 UE 統計失敗", imsi=imsi, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "取得 UE 統計失敗", "message": str(e)},
        )


@app.get("/api/v1/ue", response_model=List[UEInfoResponse], tags=["UE 管理"])
async def list_ues():
    """
    列出所有已註冊的 UE

    Returns:
        所有 UE 的資訊列表
    """
    try:
        ue_service = app.state.ue_service
        ues = await ue_service.list_all_ues()

        return [UEInfoResponse(**ue) for ue in ues]

    except Exception as e:
        logger.error("列出 UE 失敗", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "列出 UE 失敗", "message": str(e)},
        )


# ===== Slice 管理端點 =====


@app.post(
    "/api/v1/slice/switch", response_model=SliceSwitchResponse, tags=["Slice 管理"]
)
async def switch_slice(request: SliceSwitchRequest):
    """
    切換 UE 的 Network Slice

    Args:
        request: Slice 切換請求，包含 IMSI 和目標 Slice

    Returns:
        切換結果和新的 Slice 資訊
    """
    try:
        slice_service = app.state.slice_service

        # 記錄切換請求
        logger.info(
            "收到 Slice 切換請求", imsi=request.imsi, target_slice=request.target_slice
        )

        # 將字串轉換為 SliceType 枚舉
        try:
            target_slice_enum = SliceType(request.target_slice)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支援的 Slice 類型: {request.target_slice}",
            )

        # 執行切換
        result = await slice_service.switch_slice(
            imsi=request.imsi, target_slice=target_slice_enum
        )

        if not result.get("success", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Slice 切換失敗"),
            )

        # 更新指標
        SLICE_SWITCH_COUNT.labels(
            from_slice=result.get("previous_slice", "unknown"),
            to_slice=request.target_slice,
            status="success",
        ).inc()

        logger.info(
            "Slice 切換成功", imsi=request.imsi, target_slice=request.target_slice
        )

        # 構建回應
        from .models.responses import SliceInfo

        previous_slice_info = SliceInfo(
            sst=1 if result.get("previous_slice") == "eMBB" else 2,
            sd="0x111111" if result.get("previous_slice") == "eMBB" else "0x222222",
            slice_type=result.get("previous_slice", "unknown"),
        )

        new_slice_info = SliceInfo(
            sst=1 if result.get("current_slice") == "eMBB" else 2,
            sd="0x111111" if result.get("current_slice") == "eMBB" else "0x222222",
            slice_type=result.get("current_slice"),
        )

        return SliceSwitchResponse(
            imsi=request.imsi,
            previous_slice=previous_slice_info,
            new_slice=new_slice_info,
            success=True,
            message=result.get("message", "Slice 切換成功"),
        )

    except HTTPException:
        # 更新失敗指標
        SLICE_SWITCH_COUNT.labels(
            from_slice="unknown", to_slice=request.target_slice, status="error"
        ).inc()
        raise
    except Exception as e:
        logger.error(
            "Slice 切換失敗",
            imsi=request.imsi,
            target_slice=request.target_slice,
            error=str(e),
        )

        # 更新失敗指標
        SLICE_SWITCH_COUNT.labels(
            from_slice="unknown", to_slice=request.target_slice, status="error"
        ).inc()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Slice 切換失敗", "message": str(e)},
        )


@app.get("/api/v1/slice/types", tags=["Slice 管理"])
async def get_slice_types():
    """
    取得可用的 Slice 類型

    Returns:
        支援的 Slice 類型列表及其配置
    """
    try:
        slice_service = app.state.slice_service
        slice_info = await slice_service.get_slice_types()

        return slice_info

    except Exception as e:
        logger.error("取得 Slice 類型失敗", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "取得 Slice 類型失敗", "message": str(e)},
        )


# ===== 錯誤處理 =====


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """HTTP 異常處理器"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="HTTP Error", message=exc.detail, status_code=exc.status_code
        ).dict(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """一般異常處理器"""
    logger.error("未處理的異常", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal Server Error", message="系統內部錯誤", status_code=500
        ).dict(),
    )


# ===== 根路徑 =====


@app.get("/", tags=["基本資訊"])
async def root():
    """API 根路徑，回傳基本資訊"""
    return {
        "name": "NetStack API",
        "version": "1.0.0",
        "description": "Open5GS + UERANSIM 雙 Slice 核心網管理 API",
        "docs_url": "/docs",
        "health_url": "/health",
        "metrics_url": "/metrics",
        "github": "https://github.com/yourorg/netstack",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True, log_level="info")
