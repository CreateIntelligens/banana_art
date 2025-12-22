# Banana Art 🍌

這是一個使用 Google Gemini API (Flash/Pro/Vision) 打造的全端 AI 圖片生成應用程式。
具備簡潔的 React 前端介面，支援圖片管理、上傳、模板應用以及長寬比調整等功能。

## 功能特色

- **多模態生成 (Multi-Modal Generation)**:
  - **文生圖 (Text-to-Image)**: 輸入純文字提示詞即可生成圖片。
  - **圖生圖 (Image-to-Image)**: 上傳參考圖片並搭配提示詞進行修改或風格轉換。
  - **多圖輸入**: 支援選擇多張圖片作為輸入，Gemini 模型將會同時參考這些圖片。
- **模板系統 (Template System)**:
  - 能夠將常用的 Prompt 和參考圖片儲存為模板。
  - 支援「套用模板」功能，將您的圖片與模板的風格圖片結合。
- **進階控制**: 支援多種長寬比設定 (1:1, 16:9, 9:16 等)。
- **畫廊系統 (Gallery System)**:
  - 瀏覽所有生成歷史紀錄。
  - 並排對照檢視: 顯示輸入原圖 (IN 1, IN 2...) 與生成結果 (OUT)。
  - 全螢幕燈箱 (Lightbox): 支援大圖檢視、查看解析度資訊及下載圖片。
- **管理功能**:
  - 可刪除不滿意的生成結果。
  - 可刪除上傳的原始圖片（點擊圖片右下角的垃圾桶）。

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
   GEMINI_MODEL_NAME=gemini-2.0-flash-exp  # 建議使用最新版模型
   ```

3. **啟動應用程式**
   使用 Docker Compose 啟動服務:
   ```bash
   docker compose up --build
   ```

4. **開始使用**
   - **前端頁面**: [http://localhost:5173](http://localhost:5173) (若使用 Docker 預設 port)
   - **後端 API 文件**: [http://localhost:7588/docs](http://localhost:7588/docs)

## 使用指南

### 1. 創作 (Create)
自由創作模式，適合從頭開始生成。

- **輸入圖片**:
  - 點擊圖片即可選取，再次點擊取消。
  - **順序很重要**: 圖片上會顯示 **1, 2, 3...** 的數字，這代表傳送給 AI 模型的順序。
  - 提示詞範例: "Make image 1 and image 2 playing cards..."。
- **管理圖片**:
  - 點擊圖片**右上角**放大鏡：檢視大圖。
  - 點擊圖片**右下角**垃圾桶：永久刪除該圖片。

### 2. 套用模板 (Apply Template)
將您的圖片融合到既有的風格模板中。

- **操作流程**:
  1. 先選擇一個模板 (Template)。
  2. 再選擇您要上傳或使用的圖片 (User Images)。
- **API 圖片處理順序**:
  當您點擊生成時，系統會依照以下順序將圖片傳送給模型：
  1. **使用者圖片 (User Images)**: 依照您選取的順序 (1, 2...)。
  2. **模板圖片 (Template Images)**: 模板原本設定的參考圖。
  
  *範例*: 如果您選了兩張圖 (A, B) 並套用了一個有一個參考圖 (T) 的模板，模型看到的順序是: `[A, B, T]`。

### 3. 模板管理 (Templates)
- 建立您自己的風格模板。
- 設定預設的 Prompt（支援 `{{prompt}}` 語法佔位，雖然目前簡易版尚未完全實作變數替換，但可作為紀錄）。
- 綁定參考圖片與長寬比。

### 4. 畫廊 (Gallery)
- 檢視所有歷史紀錄。
- **輸入顯示**: 左側會列出該次生成所使用的所有輸入圖片 (IN 1, IN 2...)，順序與生成時一致。
- **結果顯示**: 右側為生成結果 (OUT)。
- 點擊圖片可放大檢視並下載。

## 最近更新與修復

### 前端介面優化 (2025-12-19)
- **修正圖片重疊問題**: 針對模板管理頁面 (Templates) 的「Reference Images」區域進行了佈局修復。
  - **問題**: 原本在窄螢幕或圖片過多時，格狀佈局縮圖會發生上下行重疊，導致無法正確點擊選擇。
  - **修復方案**: 採用了穩定性更高的 **Padding Hack** 技術 (`h-0 pb-[100%]`)，強制維持每列 4 個的正方形比例，確保佈局不再塌陷或重疊。
  - **可操作性**: 確保了所有縮圖作為按鈕使用時，點擊區域正確且互不干擾。

## API 參考 (API Reference)
- `GET /api/images`: 取得已上傳的原始圖片列表。

### 直接生成 API (Direct Generation APIs)
適合外部整合或腳本使用，無需先呼叫 `/upload`。

**1. 直接生成 (Direct Generate)**
```bash
curl -X POST "http://localhost:7588/api/generate-direct" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "prompt=A futuristic city with flying cars" \
  -F "aspect_ratio=16:9" \
  -F "files=@/path/to/image1.jpg" \
  -F "files=@/path/to/image2.png"
```

**2. 直接套用模板 (Direct Template)**
```bash
curl -X POST "http://localhost:7588/api/generations/from-template-direct" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "template_id=1" \
  -F "files=@/path/to/user_photo.jpg"
```

## 專案構造

```
banana-art/
├── backend/            # FastAPI 後端應用
│   ├── static/         # 靜態檔案 (uploads/ & generated/)
│   ├── main.py         # 核心邏輯 API
│   └── models.py       # DB Schema
├── frontend/           # React 前端應用
│   ├── src/            # App.tsx, api.ts
│   └── vite.config.ts  # Vite Config
└── docker-compose.yaml # 服務編排
```
