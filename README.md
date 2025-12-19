# Banana Art 🍌

這是一個使用 Google Gemini API (Flash/Pro/Vision) 打造的全端 AI 圖片生成應用程式。
具備簡潔的 React 前端介面，支援圖片管理、上傳以及長寬比調整等功能。

## 功能特色

- **多模態生成 (Multi-Modal Generation)**:
  - **文生圖 (Text-to-Image)**: 輸入純文字提示詞即可生成圖片。
  - **圖生圖 (Image-to-Image)**: 上傳參考圖片並搭配提示詞進行修改或風格轉換。
- **進階控制**: 支援多種長寬比設定 (1:1, 16:9, 9:16 等)。
- **畫廊系統 (Gallery System)**:
  - 瀏覽所有生成歷史紀錄。
  - 並排對照檢視 (Before/After): 同時顯示輸入原圖與生成結果。
  - 全螢幕燈箱 (Lightbox): 支援大圖檢視、查看解析度資訊及下載圖片。
  - 管理功能: 可刪除不滿意的生成結果（保留原始上傳圖片）。
- **即時反饋**: 顯示生成進度與詳細的前端操作日誌 (Logs)。

## 技術堆疊 (Tech Stack)

- **後端**: Python FastAPI, SQLite, SQLAlchemy, Google Generative AI SDK.
- **前端**: React (Vite), TypeScript, Tailwind CSS, Lucide Icons.
- **基礎建設**: Docker Compose.

## 前置需求

- Docker & Docker Compose
- Google Gemini API Key

## 安裝與執行

1. **Clone 專案**
   ```bash
   git clone <your-repo-url>
   cd banana-art
   ```

2. **設定環境變數**
   在專案根目錄建立 `.env` 檔案 (可複製 `.env.example`):
   ```bash
   cp .env.example .env
   ```
   編輯 `.env` 並填入您的 API Key:
   ```ini
   GEMINI_API_KEY=您的_API_KEY
   GEMINI_MODEL_NAME=gemini-3-pro-preview  # 或 gemini-2.0-flash
   ```

3. **啟動應用程式**
   使用 Docker Compose 啟動服務:
   ```bash
   docker compose up --build
   ```

4. **開始使用**
   - **前端頁面**: [http://localhost:5173](http://localhost:5173)
   - **後端 API 文件**: [http://localhost:8000/docs](http://localhost:8000/docs)

## 使用指南

### 前端介面 (Frontend)
1. **創作頁籤 (Create Tab)**:
   - **選擇輸入圖片 (可選)**:
     - 點擊 "Upload New" 方塊上傳本地圖片。
     - 從右側的網格中選擇先前上傳過的圖片。
     - 點擊圖片右上角的放大鏡圖示可檢視原圖細節。
   - **輸入提示詞 (Prompt)**: 描述您想要生成的內容。
   - **長寬比 (Aspect Ratio)**: 從下拉選單選擇圖片比例 (如 Square, Landscape, Portrait)。
   - 點擊 **Generate** 按鈕。生成結果完成後會自動顯示在下方。

2. **畫廊頁籤 (Gallery Tab)**:
   - 瀏覽所有過去的創作。
   - 若該次生成有參考原圖，卡片會以分割畫面顯示 (左:原圖 / 右:成品)。
   - 點擊卡片開啟 **全螢幕檢視模式**:
     - 檢視高解析度大圖。
     - 查看圖片實際解析度 (例如 1024x1024 px)。
     - 下載生成結果。
   - 使用垃圾桶圖示刪除紀錄 (此操作僅刪除生成結果，不會刪除原始上傳的圖片)。

### 後端 API (Backend)
後端基於 FastAPI 建構，提供以下主要 Endpoints:

- `POST /api/upload`: 上傳原始圖片。
- `POST /api/generate`: 觸發生成任務 (支援可選的 `image_id` 與 `aspect_ratio`)。
- `GET /api/history`: 取得生成歷史列表。
- `GET /api/generations/{id}`: 取得單筆生成任務詳情 (用於輪詢狀態)。
- `DELETE /api/generations/{id}`: 刪除生成紀錄。
- `GET /api/images`: 取得已上傳的原始圖片列表。

## 專案結構

```
banana-art/
├── backend/            # FastAPI 後端應用
│   ├── static/         # 靜態檔案儲存 (上傳圖檔 & 生成圖檔)
│   ├── logs/           # 應用程式日誌
│   ├── main.py         # 程式入口與核心邏輯
│   └── models.py       # 資料庫模型定義
├── frontend/           # React 前端應用
│   ├── src/            # 元件與邏輯程式碼
│   └── vite.config.ts  # Vite 設定檔
└── docker-compose.yaml # Docker 編排設定
```

## 疑難排解 (Troubleshooting)

- **500 Internal Server Error (Database)**:
  如果您修改了資料庫模型 (Schema)，請嘗試刪除 `backend/banana_art.db` 檔案並重啟容器，讓系統重新建立資料庫結構。
- **Quota Exceeded (配額不足)**:
  Gemini 免費層級有速率限制。如果您在日誌中看到 Quota 相關錯誤，請嘗試在 `.env` 中將 `GEMINI_MODEL_NAME` 切換為 `gemini-1.5-flash` 以獲得較高的請求額度。