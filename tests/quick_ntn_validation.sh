#!/bin/bash

# NetStack NTN 功能快速驗證腳本
# 快速檢查新增的NTN功能是否正確實現

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🛰️  NetStack NTN 功能快速驗證${NC}"
echo "=========================================="

# 1. 檢查配置文件是否包含NTN優化
echo -e "${BLUE}[1/6] 檢查AMF配置中的NTN計時器${NC}"
if grep -q "t3502:" ../config/amf.yaml && grep -q "satellite_mode:" ../config/amf.yaml; then
    echo -e "  ${GREEN}✅ AMF NTN計時器優化已配置${NC}"
else
    echo -e "  ${RED}❌ AMF NTN配置缺失${NC}"
fi

echo -e "${BLUE}[2/6] 檢查SMF配置中的NTN QoS${NC}"
if grep -q "ntn_config:" ../config/smf.yaml && grep -q "qos_profiles:" ../config/smf.yaml; then
    echo -e "  ${GREEN}✅ SMF NTN QoS優化已配置${NC}"
else
    echo -e "  ${RED}❌ SMF NTN配置缺失${NC}"
fi

echo -e "${BLUE}[3/6] 檢查NSSF配置中的NTN切片選擇${NC}"
if grep -q "ntn_slice_selection:" ../config/nssf.yaml && grep -q "uav_types:" ../config/nssf.yaml; then
    echo -e "  ${GREEN}✅ NSSF NTN切片選擇已配置${NC}"
else
    echo -e "  ${RED}❌ NSSF NTN配置缺失${NC}"
fi

# 2. 檢查新增的Python模型和服務
echo -e "${BLUE}[4/6] 檢查UERANSIM模型文件${NC}"
if [ -f "../netstack_api/models/ueransim_models.py" ]; then
    if grep -q "ScenarioType" "../netstack_api/models/ueransim_models.py"; then
        echo -e "  ${GREEN}✅ UERANSIM模型已實現${NC}"
    else
        echo -e "  ${YELLOW}⚠️  UERANSIM模型不完整${NC}"
    fi
else
    echo -e "  ${RED}❌ UERANSIM模型缺失${NC}"
fi

echo -e "${BLUE}[5/6] 檢查UERANSIM服務文件${NC}"
if [ -f "../netstack_api/services/ueransim_service.py" ]; then
    if grep -q "UERANSIMConfigService" "../netstack_api/services/ueransim_service.py"; then
        echo -e "  ${GREEN}✅ UERANSIM服務已實現${NC}"
    else
        echo -e "  ${YELLOW}⚠️  UERANSIM服務不完整${NC}"
    fi
else
    echo -e "  ${RED}❌ UERANSIM服務缺失${NC}"
fi

# 3. 檢查API端點是否已添加
echo -e "${BLUE}[6/6] 檢查API端點配置${NC}"
if grep -q "/api/v1/ueransim/config/generate" "../netstack_api/main.py"; then
    echo -e "  ${GREEN}✅ UERANSIM配置端點已添加${NC}"
else
    echo -e "  ${RED}❌ UERANSIM配置端點缺失${NC}"
fi

# 統計新增的功能
echo ""
echo -e "${BLUE}📊 新增功能統計：${NC}"
echo "=========================================="

# AMF計時器數量
amf_timers=$(grep -c "t35[0-9][0-9]:" ../config/amf.yaml 2>/dev/null || echo 0)
echo -e "  📡 AMF NTN計時器: ${amf_timers} 個"

# SMF QoS配置文件數量  
smf_qos=$(grep -c "slice_sst:" ../config/smf.yaml 2>/dev/null || echo 0)
echo -e "  🎯 SMF QoS配置文件: ${smf_qos} 個"

# NSSF UAV類型映射數量
nssf_uav=$(grep -c "UAV-.*-" ../config/nssf.yaml 2>/dev/null || echo 0)
echo -e "  🚁 NSSF UAV類型映射: ${nssf_uav} 個"

# 場景類型數量
if [ -f "../netstack_api/models/ueransim_models.py" ]; then
    scenarios=$(grep -c ".*_SATELLITE\|.*_FLIGHT\|.*_HANDOVER\|.*_UPDATE" ../netstack_api/models/ueransim_models.py 2>/dev/null || echo 0)
    echo -e "  🎬 支援場景類型: ${scenarios} 個"
fi

# 測試腳本數量
test_scripts=$(ls -1 *test*.sh *ntn*.sh 2>/dev/null | wc -l)
echo -e "  🧪 測試腳本: ${test_scripts} 個"

echo ""
echo -e "${BLUE}🏆 NTN功能實現總結：${NC}"
echo "=========================================="

# 功能完成度評估
total_features=6
completed_features=0

# 檢查各項功能
features=(
    "AMF NTN計時器優化"
    "SMF NTN QoS配置"
    "NSSF NTN切片選擇"
    "UERANSIM動態配置模型"
    "UERANSIM配置服務"
    "動態配置API端點"
)

checks=(
    "grep -q 't3502:' ../config/amf.yaml"
    "grep -q 'ntn_config:' ../config/smf.yaml"
    "grep -q 'ntn_slice_selection:' ../config/nssf.yaml"
    "[ -f '../netstack_api/models/ueransim_models.py' ]"
    "[ -f '../netstack_api/services/ueransim_service.py' ]"
    "grep -q '/api/v1/ueransim/config/generate' ../netstack_api/main.py"
)

for i in "${!features[@]}"; do
    if eval "${checks[$i]}" 2>/dev/null; then
        echo -e "  ${GREEN}✅ ${features[$i]}${NC}"
        ((completed_features++))
    else
        echo -e "  ${RED}❌ ${features[$i]}${NC}"
    fi
done

# 計算完成百分比
completion_percentage=$((completed_features * 100 / total_features))

echo ""
echo -e "${BLUE}📈 實現進度: ${completed_features}/${total_features} (${completion_percentage}%)${NC}"

if [ $completion_percentage -eq 100 ]; then
    echo -e "${GREEN}🎉 所有NTN功能已完成實現！${NC}"
elif [ $completion_percentage -ge 80 ]; then
    echo -e "${YELLOW}⚡ NTN功能基本完成，還有少量工作需要完善${NC}"
elif [ $completion_percentage -ge 60 ]; then
    echo -e "${YELLOW}🔧 NTN功能部分完成，需要繼續開發${NC}"
else
    echo -e "${RED}🚧 NTN功能尚在開發中，需要大量工作${NC}"
fi

echo ""
echo -e "${BLUE}💡 建議下一步：${NC}"
echo "  1. 啟動NetStack API服務測試新端點"
echo "  2. 運行完整的E2E測試驗證整合"
echo "  3. 測試真實衛星-UAV場景"
echo "  4. 添加更多性能監控指標"
echo "  5. 完善錯誤處理和恢復機制"

echo ""
echo "=========================================="
echo -e "${BLUE}🛰️  NTN功能快速驗證完成${NC}" 