 # TradingView Scraper - Browser Automation Implementation Plan

## 问题背景

当前 TradingView scraper 无法从页面 URL 直接获取 PineScript 源码，因为：

1. **页面 URL**: `https://www.tradingview.com/script/Lw0d0Ny4-Swing-Structure-Bands-ChartPrime/`
2. **页面 HTML 中的 ID**: `uuid: "Lw0d0Ny4"`, `id: 21298051`
3. **实际 API 需要的 ID**: `PUB;83b6a0ad45b54b2fb00bc0a4cee7aa73` (在 HTML 中找不到)
4. **可用的 API**: `https://pine-facade.tradingview.com/pine-facade/get/PUB%3B83b6a0ad45b54b2fb00bc0a4cee7aa73/1?no_4xx=true`

问题核心：**如何从页面 URL 获取到 `PUB;xxx` 格式的 script ID？**

---

## 解决方案：浏览器自动化

使用 Playwright 模拟用户操作，拦截网络请求获取真实的 API URL。

---

## 实现任务清单

### Phase 1: 环境准备

- [ ] **安装 Playwright**
  ```bash
  cd packages/tradingview_scraper
  pip install playwright
  playwright install chromium  # 只安装 chromium 浏览器
  ```

- [ ] **更新依赖配置**
  - 文件: `packages/tradingview_scraper/pyproject.toml`
  - 添加依赖: `playwright = "^1.40.0"`
  - 添加可选依赖组: `[tool.poetry.extras]` `automation = ["playwright"]`

- [ ] **在 Docker 镜像中安装浏览器**
  - 文件: `infra/images/api/Dockerfile`
  - 添加 Playwright 浏览器安装命令
  - 注意：需要安装系统依赖（chromium 需要的 libs）

---

### Phase 2: 实现浏览器自动化 Scraper

- [ ] **创建新的 Scraper 类**
  - 文件: `packages/tradingview_scraper/tradingview_scraper/browser_scraper.py`
  - 类名: `PlaywrightScraper`
  - 继承或组合现有的 `PineScriptScraper`

- [ ] **核心功能实现**

#### 2.1 初始化浏览器

```python
from playwright.sync_api import sync_playwright, Browser, Page
import logging

logger = logging.getLogger(__name__)

class PlaywrightScraper:
    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Args:
            headless: 是否无头模式运行（生产环境必须 True）
            timeout: 页面加载超时时间（毫秒）
        """
        self.headless = headless
        self.timeout = timeout
        self.playwright = None
        self.browser = None

    def __enter__(self):
        """Context manager 入口"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 出口，确保资源清理"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
```

#### 2.2 拦截网络请求获取 pine-facade API

```python
def get_script_with_browser(self, script_url: str) -> Dict[str, Any]:
    """
    使用浏览器自动化获取脚本源码

    核心思路：
    1. 访问脚本页面
    2. 设置网络请求拦截器
    3. 点击 "Source Code" 按钮（如果存在）
    4. 捕获 pine-facade/get/ 的请求响应
    5. 解析并返回源码
    """
    logger.info(f"🌐 Starting browser automation for: {script_url}")

    # 存储捕获的 API 响应
    captured_responses = []

    page = self.browser.new_page()

    try:
        # 设置页面超时
        page.set_default_timeout(self.timeout)

        # 拦截网络请求
        def handle_response(response):
            url = response.url
            # 捕获 pine-facade API 请求
            if "pine-facade.tradingview.com/pine-facade/get/" in url:
                logger.info(f"✓ Captured pine-facade API request: {url}")
                try:
                    if response.status == 200:
                        data = response.json()
                        captured_responses.append({
                            'url': url,
                            'data': data
                        })
                        logger.info(f"  Response keys: {list(data.keys())}")
                        if data.get('source'):
                            logger.info(f"  ✓ Found source code! Length: {len(data['source'])}")
                except Exception as e:
                    logger.warning(f"  Failed to parse response: {e}")

        page.on("response", handle_response)

        # 访问页面
        logger.info(f"📄 Navigating to page...")
        page.goto(script_url, wait_until="domcontentloaded")

        # 等待页面加载
        page.wait_for_load_state("networkidle", timeout=10000)

        # 尝试点击 "Source Code" 按钮（多种可能的选择器）
        source_code_selectors = [
            'button:has-text("Source code")',
            'a:has-text("Source code")',
            '[data-name="source-code"]',
            '.tv-script-tab:has-text("Source")',
        ]

        clicked = False
        for selector in source_code_selectors:
            try:
                if page.locator(selector).count() > 0:
                    logger.info(f"🖱️  Clicking 'Source Code' button: {selector}")
                    page.click(selector, timeout=5000)
                    clicked = True
                    # 等待网络请求完成
                    page.wait_for_timeout(2000)
                    break
            except Exception as e:
                logger.debug(f"  Selector '{selector}' not found or failed: {e}")

        if not clicked:
            logger.warning("⚠️  'Source Code' button not found, checking captured responses...")

        # 检查是否捕获到响应
        if captured_responses:
            logger.info(f"✓ Successfully captured {len(captured_responses)} API response(s)")
            # 返回第一个有效的响应
            for resp in captured_responses:
                if resp['data'].get('source'):
                    return self._normalize_browser_response(resp['data'], script_url)

        # 如果没有捕获到，返回错误
        logger.error("✗ Failed to capture pine-facade API response")
        return {
            'url': script_url,
            'error': 'Failed to capture script source via browser automation'
        }

    finally:
        page.close()

def _normalize_browser_response(self, data: Dict, script_url: str) -> Dict[str, Any]:
    """规范化浏览器捕获的响应"""
    return {
        'id': data.get('id', ''),
        'url': script_url,
        'name': data.get('scriptName', ''),
        'description': data.get('description', ''),
        'author': data.get('author', ''),
        'source': data.get('source', ''),
        'scriptAccess': data.get('scriptAccess', ''),
        'version': data.get('version', ''),
        'created': data.get('created', ''),
        'updated': data.get('updated', ''),
    }
```

---

### Phase 3: 集成到现有 Scraper

- [ ] **更新 `scraper.py` 主类**
  - 文件: `packages/tradingview_scraper/tradingview_scraper/scraper.py`
  - 在 `get_script()` 方法中添加浏览器自动化作为最后的 fallback

```python
def get_script(self, script_url: str) -> Dict[str, Any]:
    """Scrape PineScript from a TradingView script URL."""
    logger.info(f"Starting to scrape TradingView script: {script_url}")

    script_id = self._extract_script_id(script_url)
    if not script_id:
        raise ValueError(f"Invalid TradingView script URL: {script_url}")

    result = None

    # 1. Try API endpoint first (fast)
    try:
        result = self._fetch_via_api(script_id, script_url)
        if result and result.get("source"):
            logger.info(f"✓ Successfully fetched via API")
            return result
    except Exception as e:
        logger.warning(f"API method failed: {e}")

    # 2. Try HTML parsing (medium speed)
    try:
        result = self._fetch_via_html(script_url, script_id)
        if result and result.get("source"):
            logger.info(f"✓ Successfully fetched via HTML")
            return result
    except Exception as e:
        logger.warning(f"HTML method failed: {e}")

    # 3. Fallback to browser automation (slow but reliable)
    try:
        logger.info("🌐 Attempting browser automation as last resort...")
        from tradingview_scraper.browser_scraper import PlaywrightScraper

        with PlaywrightScraper(headless=True) as browser_scraper:
            result = browser_scraper.get_script_with_browser(script_url)
            if result and result.get("source"):
                logger.info(f"✓ Successfully fetched via browser automation")
                return result
    except ImportError:
        logger.warning("Playwright not installed, skipping browser automation")
    except Exception as e:
        logger.error(f"Browser automation failed: {e}")

    # All methods failed
    return {
        "id": script_id,
        "url": script_url,
        "error": "Unable to fetch script. All methods failed.",
    }
```

---

### Phase 4: 环境变量配置

- [ ] **添加配置选项**
  - 文件: `services/api/app/settings.py`
  - 添加环境变量:
    ```python
    TRADINGVIEW_USE_BROWSER_AUTOMATION: bool = Field(
        default=False,
        description="Enable browser automation for TradingView scraping (slower but more reliable)"
    )
    TRADINGVIEW_BROWSER_HEADLESS: bool = Field(
        default=True,
        description="Run browser in headless mode"
    )
    ```

- [ ] **在 `.env` 文件中配置**
  - 文件: `infra/compose/.env`
  ```bash
  # TradingView Scraper Settings
  TRADINGVIEW_USE_BROWSER_AUTOMATION=false  # 默认关闭，需要时手动开启
  TRADINGVIEW_BROWSER_HEADLESS=true
  ```

---

### Phase 5: Docker 配置优化

- [ ] **更新 API Docker 镜像**
  - 文件: `infra/images/api/Dockerfile`

```dockerfile
# 添加 Playwright 系统依赖
RUN apt-get update && apt-get install -y \
    # Chromium 依赖
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Playwright 浏览器
RUN pip install playwright && \
    playwright install chromium --with-deps
```

- [ ] **优化 Docker 镜像大小**
  - 考虑使用多阶段构建
  - 只在需要时安装 Playwright
  - 或者创建独立的 worker 镜像专门处理浏览器自动化任务

---

### Phase 6: 性能优化

- [ ] **实现缓存机制**
  - 缓存已获取的 script ID 映射关系
  - 文件: `packages/tradingview_scraper/tradingview_scraper/cache.py`
  ```python
  # Redis 缓存 uuid -> PUB;xxx 映射
  # TTL: 7天（脚本 ID 不太会变化）
  cache_key = f"tv:script_id:{uuid}"
  ```

- [ ] **添加请求限流**
  - 避免频繁使用浏览器自动化导致被封禁
  - 每个 IP 限制每小时最多 X 次浏览器请求

- [ ] **异步化处理**
  - 使用 `playwright.async_api` 替代同步 API
  - 允许并发处理多个导入请求

---

### Phase 7: 错误处理与监控

- [ ] **添加详细的错误处理**
  ```python
  class BrowserAutomationError(Exception):
      """浏览器自动化失败"""
      pass

  class ScriptNotFoundError(Exception):
      """脚本不存在或已删除"""
      pass

  class CaptchaDetectedError(Exception):
      """检测到验证码"""
      pass
  ```

- [ ] **添加监控指标**
  - 记录每种方法的成功率
  - 记录浏览器自动化的平均耗时
  - 设置告警（失败率过高时通知）

---

### Phase 8: 测试

- [ ] **单元测试**
  - 文件: `packages/tradingview_scraper/tests/test_browser_scraper.py`
  - 测试用例:
    1. 测试公开脚本抓取
    2. 测试私有脚本（应该失败）
    3. 测试网络超时
    4. 测试无效 URL

- [ ] **集成测试**
  - 测试完整的导入流程：前端 → API → Scraper → LLM
  - 验证生成的策略代码是否正确

- [ ] **Mock 测试**
  - 使用 pytest-playwright
  - Mock TradingView 页面响应，避免依赖外部服务

---

## 替代方案（备选）

如果浏览器自动化太慢或不稳定，可以考虑：

### 方案 A: 反向工程 TradingView 前端 API

- [ ] 分析 TradingView 前端 JavaScript bundle
- [ ] 找到 `uuid` → `PUB;xxx` 的转换逻辑
- [ ] 直接调用隐藏的内部 API

### 方案 B: 使用 TradingView 官方 API（如果有）

- [ ] 调研 TradingView 是否提供官方开发者 API
- [ ] 申请 API Key
- [ ] 遵守 API 使用限制

### 方案 C: 让用户手动提供 pine-facade URL

- [ ] 修改前端 UI，增加"高级选项"
- [ ] 允许用户粘贴完整的 `pine-facade/get/` API URL
- [ ] 提供获取该 URL 的教程（打开开发者工具 → Network）

---

## 预期效果

**成功指标**:
- ✅ 能够成功导入 80%+ 的公开 TradingView 脚本
- ✅ 平均导入时间 < 30 秒
- ✅ 错误信息清晰，用户知道如何处理失败情况

**风险与限制**:
- ⚠️ TradingView 可能更新前端结构，导致选择器失效
- ⚠️ 浏览器自动化比纯 HTTP 请求慢（10-30 秒 vs 1-2 秒）
- ⚠️ Docker 镜像体积会增加（+200-300MB for Chromium）
- ⚠️ 可能触发 TradingView 的反爬虫机制（需要添加 User-Agent、延迟等）

---

## 优先级评估

**高优先级（必须实现）**:
- Phase 1: 环境准备
- Phase 2.2: 核心网络拦截逻辑
- Phase 3: 集成到现有 Scraper

**中优先级（建议实现）**:
- Phase 4: 环境变量配置
- Phase 5: Docker 配置
- Phase 7: 错误处理

**低优先级（可选）**:
- Phase 6: 性能优化（等有实际使用数据后再优化）
- Phase 8: 完整测试覆盖
- 替代方案研究

---

## 参考资料

- [Playwright 文档](https://playwright.dev/python/)
- [TradingView Pine Script 文档](https://www.tradingview.com/pine-script-docs/)
- [网络请求拦截示例](https://playwright.dev/python/docs/network#handle-requests)

---

## 估算工作量

- **Phase 1-3（核心功能）**: 4-6 小时
- **Phase 4-5（配置与部署）**: 2-3 小时
- **Phase 6-8（优化与测试）**: 4-6 小时
- **总计**: ~10-15 小时

---

## 下一步行动

1. ✅ 创建此 TODO 文档
2. ⬜ 决定是否采用浏览器自动化方案（vs 替代方案）
3. ⬜ 安装 Playwright 并进行初步测试
4. ⬜ 实现最小可行版本（MVP）
5. ⬜ 在测试环境验证
6. ⬜ 部署到生产环境

---

**文档版本**: v1.0
**创建日期**: 2026-01-21
**作者**: Claude Code Assistant
**状态**: 待实施
