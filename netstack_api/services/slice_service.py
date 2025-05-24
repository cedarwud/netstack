"""
NetStack Slice Service - 5G 網路切片管理服務

提供 eMBB 和 uRLLC 切片之間的動態切換功能，
包括 UE 切片配置更新、效能監控和狀態管理。
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

import structlog
from prometheus_client import Counter, Histogram

from ..adapters.mongo_adapter import MongoAdapter
from ..adapters.open5gs_adapter import Open5GSAdapter

logger = structlog.get_logger(__name__)

# Prometheus 指標
SLICE_SWITCH_COUNTER = Counter(
    'netstack_slice_switch_total',
    'Total number of slice switches',
    ['from_slice', 'to_slice', 'status']
)

SLICE_SWITCH_DURATION = Histogram(
    'netstack_slice_switch_duration_seconds',
    'Time taken to switch slices',
    ['slice_type']
)

SLICE_PERFORMANCE_HISTOGRAM = Histogram(
    'netstack_slice_performance_seconds',
    'Slice performance metrics',
    ['slice_type', 'metric_type']
)


class SliceType(str, Enum):
    """網路切片類型"""
    EMBB = "eMBB"
    URLLC = "uRLLC"


class SliceConfig:
    """切片配置類別"""
    
    SLICE_CONFIGS = {
        SliceType.EMBB: {
            "sst": 1,
            "sd": "0x111111",
            "name": "Enhanced Mobile Broadband",
            "description": "高頻寬、低延遲敏感度的服務",
            "max_bandwidth": "1000Mbps",
            "target_latency": "100ms",
            "reliability": "99%",
            "priority": 5,
            "qos_profile": {
                "5qi": 9,
                "arp": {"priority": 8, "preemption_capability": "NOT_PREEMPT"},
                "session_ambr": {"uplink": "1000Mbps", "downlink": "2000Mbps"}
            }
        },
        SliceType.URLLC: {
            "sst": 2,
            "sd": "0x222222", 
            "name": "Ultra-Reliable Low Latency Communications",
            "description": "超可靠、超低延遲的關鍵任務服務",
            "max_bandwidth": "100Mbps",
            "target_latency": "1ms",
            "reliability": "99.999%",
            "priority": 1,
            "qos_profile": {
                "5qi": 1,
                "arp": {"priority": 1, "preemption_capability": "MAY_PREEMPT"},
                "session_ambr": {"uplink": "100Mbps", "downlink": "100Mbps"}
            }
        }
    }
    
    @classmethod
    def get_config(cls, slice_type: SliceType) -> Dict:
        """取得切片配置"""
        return cls.SLICE_CONFIGS.get(slice_type, {})
    
    @classmethod
    def get_all_configs(cls) -> Dict[SliceType, Dict]:
        """取得所有切片配置"""
        return cls.SLICE_CONFIGS


class SliceService:
    """網路切片管理服務"""
    
    def __init__(self, mongo_adapter: MongoAdapter, open5gs_adapter: Open5GSAdapter):
        self.mongo_adapter = mongo_adapter
        self.open5gs_adapter = open5gs_adapter
        self.logger = logger.bind(service="slice_service")
        
    async def switch_slice(
        self, 
        imsi: str, 
        target_slice: SliceType,
        force: bool = False
    ) -> Dict:
        """
        切換 UE 的網路切片
        
        Args:
            imsi: UE 的 IMSI
            target_slice: 目標切片類型
            force: 是否強制切換（忽略當前狀態）
            
        Returns:
            切換結果字典
        """
        start_time = datetime.utcnow()
        
        try:
            self.logger.info(
                "開始切片切換",
                imsi=imsi,
                target_slice=target_slice.value
            )
            
            # 1. 驗證 UE 存在
            ue_info = await self._get_ue_info(imsi)
            if not ue_info:
                raise ValueError(f"UE {imsi} 不存在")
            
            current_slice = ue_info.get("current_slice")
            
            # 2. 檢查是否需要切換
            if current_slice == target_slice.value and not force:
                self.logger.info(
                    "UE 已在目標切片，無需切換",
                    imsi=imsi,
                    current_slice=current_slice
                )
                return {
                    "success": True,
                    "message": "UE 已在目標切片",
                    "imsi": imsi,
                    "current_slice": current_slice,
                    "target_slice": target_slice.value,
                    "switch_time": 0
                }
            
            # 3. 執行切片切換
            with SLICE_SWITCH_DURATION.labels(slice_type=target_slice.value).time():
                switch_result = await self._perform_slice_switch(
                    imsi, current_slice, target_slice
                )
            
            # 4. 更新 UE 記錄
            await self._update_ue_slice_info(imsi, target_slice, switch_result)
            
            # 5. 記錄指標
            SLICE_SWITCH_COUNTER.labels(
                from_slice=current_slice or "none",
                to_slice=target_slice.value,
                status="success"
            ).inc()
            
            switch_time = (datetime.utcnow() - start_time).total_seconds()
            
            self.logger.info(
                "切片切換成功",
                imsi=imsi,
                from_slice=current_slice,
                to_slice=target_slice.value,
                switch_time=switch_time
            )
            
            return {
                "success": True,
                "message": "切片切換成功",
                "imsi": imsi,
                "previous_slice": current_slice,
                "current_slice": target_slice.value,
                "switch_time": switch_time,
                "slice_config": SliceConfig.get_config(target_slice)
            }
            
        except Exception as e:
            # 記錄失敗指標
            SLICE_SWITCH_COUNTER.labels(
                from_slice=current_slice or "unknown",
                to_slice=target_slice.value,
                status="error"
            ).inc()
            
            self.logger.error(
                "切片切換失敗",
                imsi=imsi,
                target_slice=target_slice.value,
                error=str(e)
            )
            
            return {
                "success": False,
                "message": f"切片切換失敗: {str(e)}",
                "imsi": imsi,
                "target_slice": target_slice.value,
                "error": str(e)
            }
    
    async def get_slice_types(self) -> Dict:
        """取得支援的切片類型和配置"""
        return {
            "slice_types": [slice_type.value for slice_type in SliceType],
            "configurations": SliceConfig.get_all_configs()
        }
    
    async def get_slice_statistics(self, slice_type: Optional[SliceType] = None) -> Dict:
        """取得切片統計資訊"""
        try:
            stats = {}
            
            if slice_type:
                # 取得特定切片統計
                stats[slice_type.value] = await self._get_slice_stats(slice_type)
            else:
                # 取得所有切片統計
                for st in SliceType:
                    stats[st.value] = await self._get_slice_stats(st)
            
            return {
                "success": True,
                "statistics": stats,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error("取得切片統計失敗", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _get_ue_info(self, imsi: str) -> Optional[Dict]:
        """取得 UE 資訊"""
        try:
            # 從 MongoDB 查詢 UE 資訊
            ue_data = await self.mongo_adapter.find_one(
                "subscribers", 
                {"imsi": imsi}
            )
            return ue_data
        except Exception as e:
            self.logger.error("查詢 UE 資訊失敗", imsi=imsi, error=str(e))
            return None
    
    async def _perform_slice_switch(
        self, 
        imsi: str, 
        current_slice: Optional[str], 
        target_slice: SliceType
    ) -> Dict:
        """執行實際的切片切換操作"""
        
        target_config = SliceConfig.get_config(target_slice)
        
        # 1. 更新 AMF 配置
        amf_result = await self.open5gs_adapter.update_ue_slice_config(
            imsi=imsi,
            sst=target_config["sst"],
            sd=target_config["sd"],
            qos_profile=target_config["qos_profile"]
        )
        
        # 2. 更新 SMF 配置
        smf_result = await self.open5gs_adapter.update_smf_session_config(
            imsi=imsi,
            slice_config=target_config
        )
        
        # 3. 觸發 UE 重新註冊（如果需要）
        if current_slice and current_slice != target_slice.value:
            await self.open5gs_adapter.trigger_ue_reregistration(imsi)
        
        return {
            "amf_update": amf_result,
            "smf_update": smf_result,
            "config_applied": target_config
        }
    
    async def _update_ue_slice_info(
        self, 
        imsi: str, 
        target_slice: SliceType, 
        switch_result: Dict
    ) -> None:
        """更新 UE 的切片資訊記錄"""
        
        update_data = {
            "current_slice": target_slice.value,
            "slice_switch_history": {
                "timestamp": datetime.utcnow(),
                "target_slice": target_slice.value,
                "switch_result": switch_result
            },
            "last_updated": datetime.utcnow()
        }
        
        # 更新 MongoDB 記錄
        await self.mongo_adapter.update_one(
            "subscribers",
            {"imsi": imsi},
            {"$set": update_data, "$push": {"slice_history": update_data["slice_switch_history"]}}
        )
        
        # 更新 Redis 快取
        cache_key = f"ue_slice:{imsi}"
        await self.mongo_adapter.redis_client.setex(
            cache_key, 
            3600,  # 1小時過期
            target_slice.value
        )
    
    async def _get_slice_stats(self, slice_type: SliceType) -> Dict:
        """取得特定切片的統計資訊"""
        
        # 查詢使用該切片的 UE 數量
        ue_count = await self.mongo_adapter.count_documents(
            "subscribers",
            {"current_slice": slice_type.value}
        )
        
        # 查詢最近24小時的切換次數
        yesterday = datetime.utcnow() - timedelta(hours=24)
        switch_count = await self.mongo_adapter.count_documents(
            "subscribers",
            {
                "slice_history.timestamp": {"$gte": yesterday},
                "slice_history.target_slice": slice_type.value
            }
        )
        
        # 取得切片配置
        config = SliceConfig.get_config(slice_type)
        
        return {
            "slice_type": slice_type.value,
            "active_ues": ue_count,
            "switches_24h": switch_count,
            "configuration": config,
            "performance_metrics": await self._get_slice_performance_metrics(slice_type)
        }
    
    async def _get_slice_performance_metrics(self, slice_type: SliceType) -> Dict:
        """取得切片效能指標"""
        
        # 這裡可以整合實際的效能監控系統
        # 目前回傳模擬數據
        
        if slice_type == SliceType.EMBB:
            return {
                "average_latency_ms": 95,
                "peak_bandwidth_mbps": 950,
                "packet_loss_rate": 0.01,
                "availability_percent": 99.2
            }
        elif slice_type == SliceType.URLLC:
            return {
                "average_latency_ms": 2,
                "peak_bandwidth_mbps": 85,
                "packet_loss_rate": 0.0001,
                "availability_percent": 99.999
            }
        
        return {} 