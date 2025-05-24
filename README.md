📋 專案結構概覽

netstack/
├── 📁 compose/ # Docker Compose 配置
│ ├── core.yaml # 核心網服務 (MongoDB, Open5GS, API, Redis, Prometheus)
│ └── ran.yaml # RAN 模擬器 (gNB, UE)
├── 📁 docker/ # 容器化配置
│ ├── Dockerfile # 多階段建置 (生產/開發環境)
│ └── healthcheck.sh # 健康檢查腳本
├── 📁 netstack_api/ # FastAPI 應用程式 (Hexagonal Architecture)
│ ├── adapters/ # 外部服務適配器
│ │ ├── mongo_adapter.py # MongoDB 資料庫操作
│ │ ├── redis_adapter.py # Redis 快取與統計
│ │ └── open5gs_adapter.py # Open5GS 核心網管理
│ ├── services/ # 業務邏輯層
│ │ ├── health_service.py # 健康檢查服務
│ │ ├── ue_service.py # UE 管理服務
│ │ └── slice_service.py # Slice 切換服務
│ ├── models/ # 資料模型
│ │ ├── requests.py # API 請求模型
│ │ └── responses.py # API 回應模型
│ └── main.py # FastAPI 應用程式入口
├── 📁 config/ # Open5GS 與 UERANSIM 配置
│ ├── amf.yaml, smf.yaml, nssf.yaml # 核心網服務配置
│ ├── gnb1.yaml, gnb2.yaml # gNodeB 配置
│ ├── ue\*.yaml # UE 配置檔案
│ └── prometheus.yml # 監控配置
├── 📁 scripts/ # 自動化腳本
│ ├── register_subscriber.sh # 用戶註冊腳本
│ └── show_subscribers.sh # 用戶查詢腳本
├── 📁 tests/ # 測試套件
│ ├── e2e_netstack.sh # 端到端測試
│ ├── test_connectivity.sh # 網路連線測試
│ ├── slice_switching_test.sh # Slice 切換測試
│ └── performance_test.sh # 效能測試
├── Makefile # 建置與操作工具 (17 個命令)
├── README.md # 完整專案文件
├── requirements.txt # Python 依賴
└── requirements-dev.txt # 開發依賴

🚀 核心功能特色

1. 雙 Slice 架構支援
   eMBB Slice (SST=1, SD=0x111111): 高頻寬行動寬頻
   uRLLC Slice (SST=2, SD=0x222222): 超可靠低延遲通訊
   動態 Slice 切換與效能監控
2. 完整 API 端點
   GET /health - 系統健康檢查
   GET /api/v1/ue - 列出所有 UE
   GET /api/v1/ue/{imsi} - 取得 UE 資訊
   GET /api/v1/ue/{imsi}/stats - 取得 UE 統計
   POST /api/v1/slice/switch - Slice 切換
   GET /api/v1/slice/types - 取得 Slice 類型
   GET /metrics - Prometheus 指標

3. 一鍵操作工具
make up              # 🚀 啟動 NetStack
make register-subscribers  # 👤 註冊測試用戶  
make start-ran       # 📡 啟動 RAN 模擬器
make test           # 🧪 執行所有測試
make slice-switch   # 🔀 測試 Slice 切換
make status         # 📊 檢查服務狀態

4. 完整測試套件
E2E 測試: API 功能驗證、Slice 切換測試
連線測試: UE 網路連通性、DNS 解析、HTTP 連線
Slice 測試: 單次/連續/並發切換、錯誤處理
效能測試: API 響應時間、並發負載、系統資源監控
5. Hexagonal Architecture
適配器層: MongoDB、Redis、Open5GS 適配器
服務層: 健康檢查、UE 管理、Slice 管理
模型層: Pydantic 資料驗證與序列化
6. 監控與指標
Prometheus 整合: API 指標、Slice 切換統計、RTT 測量
健康檢查: 系統級健康狀態監控
效能監控: 響應時間、錯誤率、成功率追蹤
📊 測試用戶配置
系統預設註冊以下測試用戶：
| IMSI | Slice 類型 | 說明 |
|------|------------|------|
| 999700000000001-003 | eMBB | eMBB 專用用戶群組 |
| 999700000000011-013 | uRLLC | uRLLC 專用用戶群組 |
| 999700000000099 | 動態切換 | 測試用戶 (支援 Slice 切換) |

🛠️ 使用流程
1. 啟動系統:
   cd netstack
   make up                    # 啟動核心網
   make register-subscribers  # 註冊測試用戶

2. 測試連線
   make start-ran            # 啟動 RAN 模擬器
   make test-connectivity    # 測試 UE 連線

3. API 操作:
   curl http://localhost:8080/health
   curl http://localhost:8080/api/v1/ue
   # Swagger UI: http://localhost:8080/docs

4. Slice 切換
   make slice-switch         # 執行 Slice 切換測試
   # 或直接 API 呼叫
   curl -X POST http://localhost:8080/api/v1/slice/switch \
     -H "Content-Type: application/json" \
     -d '{"imsi": "999700000000099", "target_slice": "uRLLC"}'

5. 監控查看:
API 文件: http://localhost:8080/docs
Prometheus: http://localhost:9090
Open5GS WebUI: http://localhost:9999

🎯 專案完成度
✅ 核心功能 (100%): 雙 Slice 支援、API 管理、UE 註冊
✅ 容器化部署 (100%): Docker Compose 一鍵啟動
✅ API 介面 (100%): RESTful API + OpenAPI 3.1 文件
✅ 測試套件 (100%): E2E、連線、Slice、效能測試
✅ 監控整合 (100%): Prometheus 指標收集
✅ 操作工具 (100%): Makefile 自動化命令
✅ 文件撰寫 (100%): 完整 README、API 文件