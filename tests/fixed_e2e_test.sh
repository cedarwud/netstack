#!/bin/bash

# 簡化版 NetStack E2E 測試腳本
# 只檢查基本 API 功能

API_BASE_URL="http://localhost:8080"
TEST_IMSI="999700000000099"

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo "===================================================="
echo "🧪 NetStack API 簡化 E2E 測試"
echo "===================================================="

# 測試 API 健康檢查
echo -e "\n[TEST] 測試 API 健康檢查"
health_response=$(curl -s "$API_BASE_URL/health")

if [[ "$health_response" == *"healthy"* ]]; then
    echo -e "${GREEN}[INFO]${NC} ✅ 健康檢查通過"
else
    echo -e "${RED}[ERROR]${NC} ❌ 健康檢查失敗"
    exit 1
fi

# 測試列出所有 UE
echo -e "\n[TEST] 測試列出所有 UE"
ue_response=$(curl -s "$API_BASE_URL/api/v1/ue")

if [[ "$ue_response" == "["* ]]; then
    ue_count=$(echo "$ue_response" | grep -o "imsi" | wc -l)
    echo -e "${GREEN}[INFO]${NC} ✅ 成功列出 UE，共 $ue_count 個"
else
    echo -e "${RED}[ERROR]${NC} ❌ 列出 UE 失敗"
    exit 1
fi

# 測試取得 Slice 類型
echo -e "\n[TEST] 測試取得 Slice 類型"
slice_response=$(curl -s "$API_BASE_URL/api/v1/slice/types")

if [[ "$slice_response" == *"slice_types"* ]]; then
    echo -e "${GREEN}[INFO]${NC} ✅ 成功取得 Slice 類型"
else
    echo -e "${RED}[ERROR]${NC} ❌ 取得 Slice 類型失敗"
    exit 1
fi

# 測試取得指定 UE 資訊
echo -e "\n[TEST] 測試取得 UE '$TEST_IMSI' 資訊"
ue_info_response=$(curl -s "$API_BASE_URL/api/v1/ue/$TEST_IMSI")

if [[ "$ue_info_response" == *"$TEST_IMSI"* ]]; then
    echo -e "${GREEN}[INFO]${NC} ✅ 成功取得 UE 資訊"
else
    echo -e "${RED}[ERROR]${NC} ❌ 取得 UE 資訊失敗"
    exit 1
fi

echo -e "\n===================================================="
echo -e "${GREEN}🎉 所有測試通過！${NC}"
echo "===================================================="
