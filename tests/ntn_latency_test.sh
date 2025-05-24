#!/bin/bash

# NetStack NTN 高延遲場景測試腳本
# 模擬衛星通信環境下的網絡性能，測試20-50ms延遲下的系統表現

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 測試設定
API_BASE_URL="http://localhost:8080"
TEST_IMSI="999700000000050"  # 衛星-無人機用戶
SATELLITE_LATENCY_MS=30      # 模擬衛星延遲
LEO_ORBIT_PERIOD=6000        # LEO軌道週期(秒)，約100分鐘

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_test() {
    echo -e "${BLUE}[NTN-TEST]${NC} $1"
}

log_satellite() {
    echo -e "${CYAN}[SATELLITE]${NC} $1"
}

# 模擬網絡延遲函數
simulate_network_delay() {
    local delay_ms=$1
    log_satellite "模擬衛星延遲: ${delay_ms}ms"
    
    # 使用 tc (traffic control) 添加網絡延遲
    # 注意：需要 root 權限，在容器環境中可能需要調整
    if command -v tc &> /dev/null; then
        sudo tc qdisc add dev eth0 root netem delay ${delay_ms}ms 2>/dev/null || true
    else
        log_warning "tc 命令不可用，使用 sleep 模擬延遲"
        sleep $(echo "scale=3; $delay_ms/1000" | bc -l)
    fi
}

# 清除網絡延遲
clear_network_delay() {
    if command -v tc &> /dev/null; then
        sudo tc qdisc del dev eth0 root 2>/dev/null || true
        log_satellite "網絡延遲已清除"
    fi
}

# 測試高延遲環境下的註冊過程
test_registration_with_delay() {
    log_test "測試高延遲環境下的UE註冊"
    
    simulate_network_delay $SATELLITE_LATENCY_MS
    
    local start_time=$(date +%s%3N)
    
    response=$(curl -s -w "%{http_code}" --max-time 60 "$API_BASE_URL/api/v1/ue/$TEST_IMSI")
    http_code="${response: -3}"
    
    local end_time=$(date +%s%3N)
    local response_time=$((end_time - start_time))
    
    clear_network_delay
    
    if [ "$http_code" == "200" ]; then
        log_info "✅ 高延遲註冊成功，響應時間: ${response_time}ms"
        
        # 檢查是否符合NTN延遲要求（應該大於衛星延遲）
        if [ $response_time -gt $((SATELLITE_LATENCY_MS * 2)) ]; then
            log_info "  延遲符合衛星通信預期"
        else
            log_warning "  延遲低於預期，可能模擬效果不佳"
        fi
    else
        log_error "❌ 高延遲註冊失敗，HTTP狀態碼: $http_code"
        return 1
    fi
}

# 測試切片切換在高延遲下的表現
test_slice_switching_with_delay() {
    log_test "測試高延遲環境下的Slice切換"
    
    local slice_types=("eMBB" "uRLLC")
    
    for target_slice in "${slice_types[@]}"; do
        log_satellite "測試切換到 $target_slice (延遲: ${SATELLITE_LATENCY_MS}ms)"
        
        simulate_network_delay $SATELLITE_LATENCY_MS
        
        local payload=$(cat <<EOF
{
  "imsi": "$TEST_IMSI",
  "target_slice": "$target_slice"
}
EOF
)
        
        local start_time=$(date +%s%3N)
        
        response=$(curl -s -w "%{http_code}" --max-time 120 \
            -X POST \
            -H "Content-Type: application/json" \
            -d "$payload" \
            "$API_BASE_URL/api/v1/slice/switch")
        
        http_code="${response: -3}"
        body="${response%???}"
        
        local end_time=$(date +%s%3N)
        local switch_time=$((end_time - start_time))
        
        clear_network_delay
        
        if [ "$http_code" == "200" ]; then
            log_info "  ✅ 切換到 $target_slice 成功，耗時: ${switch_time}ms"
            
            # 分析切換時間
            if [ $switch_time -lt 5000 ]; then  # 5秒
                echo -e "    評等: ${GREEN}優秀${NC} (<5s)"
            elif [ $switch_time -lt 10000 ]; then  # 10秒
                echo -e "    評等: ${YELLOW}良好${NC} (<10s)"
            else
                echo -e "    評等: ${RED}需要改善${NC} (>=10s)"
            fi
        else
            log_error "  ❌ 切換到 $target_slice 失敗，HTTP狀態碼: $http_code"
            echo "  回應: $body"
        fi
        
        # 等待系統穩定
        sleep 3
    done
}

# 測試連續軌道變化下的性能
test_orbital_period_simulation() {
    log_test "模擬LEO衛星軌道週期性能測試"
    
    local test_duration=300  # 5分鐘測試
    local sample_interval=30 # 30秒採樣一次
    local current_time=0
    
    log_satellite "開始軌道週期模擬 (測試時長: ${test_duration}秒)"
    
    while [ $current_time -lt $test_duration ]; do
        # 根據軌道位置計算動態延遲 (20-50ms範圍)
        local orbit_phase=$(echo "scale=3; $current_time * 360 / $LEO_ORBIT_PERIOD" | bc -l)
        local dynamic_delay=$(echo "scale=0; 35 + 15 * s($orbit_phase * 3.14159 / 180)" | bc -l)
        
        log_satellite "軌道相位: ${orbit_phase}°, 當前延遲: ${dynamic_delay}ms"
        
        # 測試當前延遲下的API響應
        simulate_network_delay $dynamic_delay
        
        local start_time=$(date +%s%3N)
        response=$(curl -s -w "%{http_code}" --max-time 30 "$API_BASE_URL/health")
        http_code="${response: -3}"
        local end_time=$(date +%s%3N)
        local response_time=$((end_time - start_time))
        
        clear_network_delay
        
        if [ "$http_code" == "200" ]; then
            log_info "  時間: ${current_time}s, 延遲: ${dynamic_delay}ms, 響應: ${response_time}ms ✅"
        else
            log_error "  時間: ${current_time}s, 延遲: ${dynamic_delay}ms, 失敗: HTTP $http_code ❌"
        fi
        
        current_time=$((current_time + sample_interval))
        sleep $sample_interval
    done
    
    log_info "軌道週期模擬測試完成"
}

# 測試NTN特定的KPI指標
test_ntn_kpi_metrics() {
    log_test "檢查NTN相關KPI指標"
    
    # 獲取Prometheus指標
    response=$(curl -s "$API_BASE_URL/metrics")
    
    # 檢查關鍵指標是否存在
    local required_metrics=(
        "netstack_slice_rtt_seconds"
        "netstack_slice_switch_total"
        "netstack_ue_attach_total"
        "netstack_api_request_duration_seconds"
    )
    
    log_info "檢查NTN相關監控指標："
    
    for metric in "${required_metrics[@]}"; do
        if echo "$response" | grep -q "$metric"; then
            log_info "  ✅ $metric"
        else
            log_error "  ❌ $metric 指標不存在"
        fi
    done
    
    # 檢查延遲相關指標的數值範圍
    if echo "$response" | grep -q "netstack_slice_rtt_seconds"; then
        log_info "RTT指標詳情："
        echo "$response" | grep "netstack_slice_rtt_seconds" | head -5
    fi
}

# 主測試函數
main() {
    log_info "🛰️  NetStack NTN 高延遲場景測試開始"
    echo "=========================================="
    
    # 檢查必要工具
    if ! command -v bc &> /dev/null; then
        log_error "需要安裝 bc 計算工具"
        exit 1
    fi
    
    local test_results=()
    
    # 執行各項測試
    log_test "測試1: 高延遲環境下的註冊"
    if test_registration_with_delay; then
        test_results+=("註冊測試: PASS")
    else
        test_results+=("註冊測試: FAIL")
    fi
    
    echo ""
    log_test "測試2: 高延遲環境下的Slice切換"
    if test_slice_switching_with_delay; then
        test_results+=("切片切換測試: PASS")
    else
        test_results+=("切片切換測試: FAIL")
    fi
    
    echo ""
    log_test "測試3: LEO軌道週期模擬"
    if test_orbital_period_simulation; then
        test_results+=("軌道模擬測試: PASS")
    else
        test_results+=("軌道模擬測試: FAIL")
    fi
    
    echo ""
    log_test "測試4: NTN KPI指標檢查"
    if test_ntn_kpi_metrics; then
        test_results+=("KPI指標測試: PASS")
    else
        test_results+=("KPI指標測試: FAIL")
    fi
    
    # 測試結果總結
    echo ""
    echo "=========================================="
    log_info "🛰️  NTN測試結果總結："
    
    for result in "${test_results[@]}"; do
        if [[ $result == *"PASS"* ]]; then
            echo -e "  ${GREEN}✅ $result${NC}"
        else
            echo -e "  ${RED}❌ $result${NC}"
        fi
    done
    
    echo "=========================================="
    log_info "NTN高延遲場景測試完成"
}

# 清理函數
cleanup() {
    clear_network_delay
}

# 設置清理陷阱
trap cleanup EXIT

# 執行主測試
main "$@" 