# AICollector

AICollector 是一個簡單的腳本，可以每天自動收集與人工智慧相關的新聞，並將結果以 Markdown 檔案儲存在儲存庫中。

## 功能

- 從多個 RSS 來源收集前一天的 AI 新聞
- 以人類可讀的 Markdown 格式儲存在 `data/<今天年>/<今天月>/<今天日期>/<目標日期>-ai-news.md`
- 可自訂資料來源、關鍵字與時區
- 可透過 GitHub Actions 或排程工具每天自動執行
- 若設定 `OPENAI_API_KEY`，會為每篇文章額外生成適合 Threads/Twitter 的約 100 字摘要，並儲存在 `data/<今天年>/<今天月>/<今天日期>/<目標日期>-ai-news-social.txt`

## 安裝

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用方式

手動執行腳本以收集特定日期（預設為前一天）的資訊：

```bash
python collector.py --date 2024-06-01
```

執行成功後，結果會儲存在 `data/<今天年份>/<今天月份>/<今天日期>/<目標日期>-ai-news.md` 中；
也就是說，即使收集的是「前一天」的內容，檔案仍會依照執行當下的日期分類。

### 自訂資料來源

編輯 `config/feeds.yaml` 來新增或移除 RSS 來源，或調整要篩選的關鍵字與時區。

- `timezone`: 指定收集新聞時使用的時區（預設為 `Asia/Taipei`）
- `keywords`: 全域關鍵字清單，會套用至所有沒有自訂關鍵字的資料來源
- `sources`: RSS 資料來源列表
  - `name`: 來源名稱（會出現在輸出的 Markdown 中）
  - `url`: RSS feed 的 URL
  - `keywords`: （可選）自訂關鍵字。使用空陣列 `[]` 代表不進行關鍵字篩選。

## 自動化

若要每天自動收集資料，可以使用以下兩種方式之一：

### 1. GitHub Actions

此儲存庫已包含 `.github/workflows/collect_ai_news.yml`，預設會以排程事件在每日 06:00（台北時間）執行一次。啟用方式如下：

1. 將儲存庫推送到 GitHub 並確認預設分支（通常是 `main`）已啟用。
2. 在 GitHub 網站進入 `Settings > Actions > General`，將 **Workflow permissions** 設為 **Read and write permissions**，以便使用預設的 `GITHUB_TOKEN` 提交變更。
3. 如果希望立即驗證，可在 Actions 頁面手動觸發 `Collect AI News` workflow 的 `Run workflow` 按鈕，它會使用與排程相同的步驟產生報告。
4. GitHub Actions 之後會根據 `schedule` 設定的 cron 表達式自動運行腳本並提交新的 Markdown 檔案。

若要調整排程時間，可以編輯 workflow 中的 `cron` 表達式，例如：

```yaml
on:
  schedule:
    - cron: '0 1 * * *'  # 每日 09:00（台北時間）執行
```

cron 時間以 UTC 計算，可參考 [crontab.guru](https://crontab.guru) 或將台北時間減 8 小時後設定。

### 2. 本地排程（Cron）

也可以在本地或伺服器上設定 cron job：

```cron
0 6 * * * cd /path/to/AICollector && /path/to/python collector.py >> /path/to/collector.log 2>&1
```

上述排程會在每日早上 06:00 執行腳本，並將輸出寫入日誌。

## 產出範例

```markdown
# AI News for 2024-06-01 (Asia/Taipei)

Collected 5 article(s).

- [Example Article](https://example.com) — 09:30 · Google News (AI)
  > A short summary of the article.
```

## 注意事項

- RSS 來源是否提供摘要及發佈時間會影響結果。
- 若某些來源未提供發佈日期，相關文章將不會出現在輸出中。
- 可依需求調整 `feeds.yaml` 中的關鍵字與來源，或新增其他語言的 feed。
- 若要啟用社群摘要，請在執行環境設定 `OPENAI_API_KEY`，腳本會呼叫 OpenAI API 產生繁體中文摘要。
- 若希望在語言模型內容生成失敗時讓指令回傳錯誤碼，可加上 `--require-summaries` 參數。
