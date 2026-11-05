# 职安 · AI 求职安全与职业规划助手

金砖大赛 AI+ 应用创新与安全设计赛项作品 MVP。依据本项目提供的需求实现，不代表赛事官方认证或评分承诺。界面使用原生 HTML、CSS、JavaScript，后端使用 Python；按最新需求加入账号、SQLite、管理后台、AI技能树、考试错题和语音模拟面试。

**本机部署状态更新**：本地PaddleOCR已部署，DeepSeek `deepseek-flash` 已接入并通过真实合成材料调用。原有密钥从本机 `.env` 读取，管理员修改后加密保存在本机运行目录。风险和原有职业报告仅发送脱敏结构化证据；新技能树和面试功能需用户确认后发送相应岗位文本、所选技能或逐轮回答。原始文件不上传。当前目录 `.venv` 可通过 `start.bat` 或 `start.ps1` 启动。详情见 [OCR部署记录](docs/OCR_DEPLOYMENT.md) 与 [DeepSeek接入记录](docs/DEEPSEEK_SETUP.md)。

摄像头练习辅助已部署本机MediaPipe人脸与手部关键点模型，详见 [部署与使用](docs/VISION_DEPLOYMENT.md)。画面不进入资料库或云端AI，不用于身份、情绪或面试成绩判断。

## ① 项目整体架构、依赖与启动

### 整体架构

```text
本地浏览器（无外部字体、脚本、图片，无 localStorage）
  │ 同源请求 + HttpOnly 会话 Cookie + CSRF Token
  ▼
FastAPI API 层 ── 格式/长度/文件签名/类型/注入检测
  ├─ PaddleOCR → 内存图像 / 内存 PDF 渲染 → 文本与逐行置信度
  ├─ PII 规则 → 原文位置 → 敏感字段高亮 → 掩码文本导出
  ├─ 风险规则 → 0–100 规则分 → 原文线索 → 核验建议
  │    └─ 可选字符 TF-IDF + 朴素贝叶斯招聘风险分类
  ├─ 词项检索 RAG → JD 需求 / 简历证据 / 本地知识条目
  │    └─ 能力证据差距 + 4 周学习计划 + 岗位面试练习题
  └─ 官方 DeepSeek / 本机 Ollama → 脱敏证据 → JSON → 证据ID/措辞校验
       │ 不配置用户 URL、不跟随重定向、不启用工具
       ▼
内存 Session Store：账号材料缓存 + 会话重建 + 容量上限
访客：固定演示 + 30分钟闲置清空，不接收个人资料
SQLite：账号/材料解析文本/OCR信息/风险与脱敏结果/职业报告/档案/技能树/考试错题/面试文字/岗位点评/审计与运营统计
语音：浏览器识别 → 脱敏文字 → AI追问 → 浏览器语音合成
```

新增功能与操作说明见 [平台扩展说明](docs/PLATFORM_GUIDE.md)。首页、登录注册、访客演示、前台与后台已拆分。按指定默认超级用户为 admin / admin，普通注册账号一律为用户，详见平台扩展说明。

两类 AI 模型的实际角色：PaddleOCR负责文字检测/识别，DeepSeek或本机Ollama负责解释已有风险与职业证据。分数、脱敏、检索依据由确定性代码提供。附加分类器是第三模型增强，使用合成小样本，仅供教学演示，未经真实招聘数据集验证，不报告诈骗概率。

安全限制：

- 只接受 PNG、JPEG、PDF；扩展名、Content-Type、文件签名必须一致。单文件最多 8 MB、PDF 最多 8 页、图像或渲染页最多 1200 万像素、材料最多 30000 字。
- 上传接口接收原始二进制请求体，按块限长；不使用 `UploadFile`、临时目录或磁盘溢出缓存。PDF 使用内存字节解码，不处理链接、脚本或附件。
- 原始上传文件二进制用于即时解析，不额外保留文件副本。正式账号的解析文本和结果会持久化到SQLite；使用DeepSeek时发送脱敏结构化证据，云端服务自身的数据处理政策需另行了解。用户在个人中心主动保存的脱敏摘要、学习与面试文字记录保存在SQLite，可单独删除。正式账号采用服务端Session和7天闲置滑动续期，访客演示30分钟闲置清空。每会话最多24份材料、64个会话、200条审计，最多2个并行模型任务。
- 仅绑定 `127.0.0.1`；单 worker。Cookie 为 HttpOnly + SameSite Strict；写入请求验证 CSRF；限制 Host/Origin；禁止外部前端资源；用户输入用文本节点渲染。
- 审计只包含时间、动作、状态和数量；不含文件名、原文、敏感值。清空移除当前会话材料与历史日志，只留下本次清空的无内容记录。代数保护阻止在途任务清空后写回。
- 不提供网页抓取、URL上传或任意代理接口。模型只连接固定回环Ollama或白名单官方 `api.deepseek.com` HTTPS接口，不跟随重定向、不启用搜索/抓取/工具。浏览器只请求本机后端，不接触API密钥。应用不会下载模型，也不会打开材料中的链接。
- Python 内存释放不等于物理内存安全擦除；操作系统交换文件、浏览器扩展和本机 Ollama 的独立配置不受本应用控制。本地 MVP 不应直接暴露到公网。

### 依赖清单

| 依赖 | 用途 | 是否必需 |
|---|---|---|
| Python 3.10–3.12 | 服务运行环境 | 是，建议 3.12 |
| FastAPI、Uvicorn | API 与单进程本机服务 | 是 |
| Pillow、NumPy | 内存图像解码与像素校验 | 是 |
| pypdfium2 | 内存 PDF 渲染 | 是 |
| python-dotenv | 读取本机环境配置 | 是 |
| PaddlePaddle 3.x、PaddleOCR 3.x | 真实 OCR 推理 | 完整演示必需 |
| DeepSeek API 或 Ollama本机模型 | 真实 LLM 推理 | 二选一；当前使用DeepSeek |
| scikit-learn | 可选文本分类增强 | 可选 |
| pytest、httpx | 安全与接口测试 | 开发验证使用 |

依赖范围见 [requirements.txt](requirements.txt) 和 [requirements-models.txt](requirements-models.txt)。实际轻量验证环境锁定文件见 `requirements-tested.txt`；本机 OCR 环境快照见 `requirements-ocr-tested.txt`。模型权重不随源码包打包，但已部署在当前本机 `models/` 目录。不会把“规则可运行”冒充“两个 AI 模型已运行”。

### 启动步骤：先启动界面与规则功能

在项目目录打开终端：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe run.py
```

如果只装了 Python 3.10，把第一条换成 `py -3.10 -m venv .venv`。也可以双击 `start.bat`：它会提示手动安装缺失依赖，不自动下载任何模型。

浏览器打开 **http://127.0.0.1:5088/**。使用“体验演示材料”可走完文字规则、隐私、RAG 和注入测试流程。此模式不调用 OCR，也不代表完成双模型竞赛演示。

端口占用时在启动前设置环境变量，例如 `$env:APP_PORT="5090"`。不启用 `--reload`、多个 worker 或公网绑定。

### 完整双模型演示的准备

1. 安装模型依赖：`.\.venv\Scripts\python.exe -m pip install -r requirements-models.txt`。PaddlePaddle 需选择与本机 Python/系统相符的 CPU 包；本项目不要求 GPU。
2. 手动准备官方 **PP-OCRv5_mobile_det** 与 **PP-OCRv5_mobile_rec** 推理模型目录，每个目录应包含配套推理配置与参数。不要把压缩包路径填作目录。应用显式指定 mobile 模型名称并关闭方向分类、文档矫正和文本行方向附加模型，避免隐式下载。
3. 选择官方DeepSeek或本机Ollama。DeepSeek配置 `LLM_PROVIDER=deepseek`、`DEEPSEEK_API_KEY` 与 `DEEPSEEK_MODEL`；本机Ollama配置 `LLM_PROVIDER=ollama` 与已安装的 `OLLAMA_MODEL`。Ollama模式只允许本地模型，不转接cloud模型。
4. 编辑 `.env`，然后重新启动后端：

```dotenv
OCR_DET_DIR=D:/models/PP-OCRv5_mobile_det
OCR_REC_DIR=D:/models/PP-OCRv5_mobile_rec
OLLAMA_MODEL=此处填写本机已安装的模型名称
LLM_PROVIDER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_API_KEY=仅在本机环境填写真实密钥
LLM_TIMEOUT=45
ENABLE_RISK_CLASSIFIER=1
```

Ollama模式无需API密钥；DeepSeek密钥只能从环境或本机 `.env` 读取，不能写入源码、前端或分享的压缩包。模型地址仅允许官方HTTPS根路径及 `/v1`，不接受任意用户URL。

模型初始化失败、服务未启动、响应超时、JSON无效、引用不存在或输出不当时，页面显示实际降级原因；鉴权、额度、限流失败不会回显上游原始错误。OCR未准备时返回明确503，不生成假文本。OCR“路径已配置”只代表目录存在，成功识别才证明推理可用。AI结果按实际来源标注“DeepSeek云端”或“本地Ollama”。

开发参考：[PaddleOCR官方参数](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.en.md)、[DeepSeek官方接口](https://api-docs.deepseek.com/)、[DeepSeek JSON输出](https://api-docs.deepseek.com/guides/json_mode/)、[Ollama生成接口](https://docs.ollama.com/api/generate)。这些是开发文档，不是应用抓取目标。

## ② Python 后端完整代码

完整可编辑源码位于 `app/`，也按用户要求顺序合并收录在 [完整源码交付文档](docs/SOURCE_BUNDLE.md)。

| 文件 | 职责 |
|---|---|
| [run.py](run.py) | 单进程、回环地址启动 |
| [app/main.py](app/main.py) | 静态页面、缓存回收、Host/Origin/CSP 安全边界 |
| [app/api.py](app/api.py) | 独立 API、受限流式上传、CSRF、错误脱敏、任务编排 |
| [app/config.py](app/config.py) | 环境变量、容量与模型配置 |
| [app/store.py](app/store.py) | 内存材料、独立会话、TTL、审计、清空代数保护 |
| [app/services/ocr.py](app/services/ocr.py) | PaddleOCR 3.x、图片/PDF、置信度与框坐标 |
| [app/services/pii.py](app/services/pii.py) | 6 类 PII 识别、重叠区间合并、完整掩码 |
| [app/services/security.py](app/services/security.py) | 注入检测、Unicode 规范化、清洗与类型判断 |
| [app/services/risk.py](app/services/risk.py) | 风险规则、否定语境、原文定位、建议 |
| [app/services/classifier.py](app/services/classifier.py) | 可选 TF-IDF + 朴素贝叶斯分类 |
| [app/services/knowledge.py](app/services/knowledge.py) | 本地示范技能知识库 |
| [app/services/career.py](app/services/career.py) | 岗位证据抽取、词项检索 RAG、差距、计划、练习题 |
| [app/services/llm.py](app/services/llm.py) | 官方DeepSeek/本机模型通信、证据脱敏、结构化输出校验 |

### API 速查

先调用 `GET /api/session` 获取会话 Cookie 和 `csrf_token`，写操作传 `X-CSRF-Token`。无跨域接口，校验错误不回显输入。

| 方法与路径 | 输入与结果 |
|---|---|
| `GET /api/session` | 会话、限制与模型状态 |
| `POST /api/materials/upload` | 原始文件字节；头部包含 Content-Type、X-File-Extension、X-Material-Type |
| `POST /api/materials/text` | `{text, kind}`；kind 为 auto/resume/recruitment/jd |
| `GET /api/materials` | 当前会话材料摘要，不返回原文列表 |
| `GET /api/materials/{id}` | 当前会话指定材料与置信度 |
| `POST /api/privacy` | `{material_id}` → 敏感区间、脱敏文本 |
| `POST /api/materials/{id}/export` | 只导出脱敏 TXT，不提供原文导出 |
| `POST /api/risk` | `{material_id}` → 规则分、高亮区间、核验建议、分类增强、LLM 状态 |
| `POST /api/career` | `{resume_id, jd_id}` → 证据差距、四周计划、题目、检索引用 |
| `POST /api/security/check` | `{text}` → 注入检测；测试材料不保存、不送 LLM |
| `GET /api/audit` | 当前会话无内容操作记录 |
| `DELETE /api/materials/{id}` | 删除一份材料并审计 |
| `DELETE /api/session/data` | 清空当前会话缓存并审计 |

### 结论边界

风险分是规则加权分，不是经过校准的诈骗概率。同类话术多次出现不重复计分，低分不等于安全。否定规则只是启发式，复杂引述、反讽、拆字和新型话术需要人工核验。

PII 是规则检测，可能漏检无标签地址、图片 OCR 错字、隐写或非标准格式。导出只有文字脱敏，不会修改原图/PDF；不要误把未处理的原文件当成脱敏文件投递。

职业“匹配”指标实际为**已识别技能中，简历是否有关键词证据的覆盖率**。不评估真实熟练度、录用概率、学历或工作年限。词表外要求明确列为待确认；没有可识别要求时不计算分数。知识库是项目编写的示范学习条目，不冒充官方岗位标准。题目是按岗位技能整理的练习题，无“真实高频”统计依据，不宣称来自某企业题库。

## ③ 前端 HTML 页面完整代码

- [static/index.html](static/index.html)：完整页面、六个视图、说明与清空对话框。
- [static/styles.css](static/styles.css)：深绿与浅色工作台、响应式、按钮反馈、短暂结果入场与减少动态偏好支持。
- [static/app.js](static/app.js)：上传、分析、高亮、对比、脱敏导出、报告、注入测试、审计与前端缓存清空。
- [static/mark.svg](static/mark.svg)：本地匿名品牌图标，无外部图片请求。

为满足 CSP 并便于维护，CSS 和 JS 从完整 HTML 中拆出，仍为原生实现，没有框架、打包工具或远程 CDN。用户材料经 `textContent` / 文本节点插入，Unicode 高亮使用码点偏移，支持 emoji 前缀。

## ④ 测试用例与演示

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check static/app.js
```

- [tests/test_services.py](tests/test_services.py)：六类 PII、重叠敏感区间、Unicode 注入、风险原文定位、否定语境、能力差距和四周依据。
- [tests/test_api.py](tests/test_api.py)：独立会话、CSRF/Origin、拦截不入库、只导出掩码、格式/大小、真实模型未配置的行为、文字流程。
- [tests/test_boundaries.py](tests/test_boundaries.py)：会话过期、容量、清空与在途任务、无 Content-Length 的流式限长、超页 PDF、OCR 协议、LLM 降级与引用/措辞校验。
- [tests/test_deepseek.py](tests/test_deepseek.py)：官方HTTPS白名单、云端证据最小化、重定向拒绝、凭据不回显、注入阻止调用及错误降级。
- [docs/DEMO.md](docs/DEMO.md)：按比赛要求顺序的操作脚本、预期现象与自检清单。
- [tests/synthetic_samples.py](tests/synthetic_samples.py)：合成招聘、简历、正常 JD 和提示注入样例，无真实身份数据。

重要区别：OCR 协议替身和模型 JSON 替身仅验证适配逻辑，不等于真实模型验证。最终双模型验收需手动准备模型，在本机上传合成截图与 PDF 并检查页面来源标识。

## ⑤ 源码目录结构

```text
career-guard/
├─ README.md                    # 按要求顺序的整体交付说明
├─ run.py                       # 本地启动入口
├─ start.bat / start.ps1         # 本地启动快捷方式
├─ .env.example                 # 环境配置模板，无密钥
├─ requirements.txt             # 轻量运行与测试依赖
├─ requirements-models.txt      # OCR 与可选分类器依赖
├─ requirements-tested.txt      # 本次验证环境版本快照
├─ app/
│  ├─ main.py / api.py / config.py / store.py
│  └─ services/
│     ├─ ocr.py / pii.py / security.py / risk.py
│     ├─ classifier.py / knowledge.py / career.py / llm.py
├─ static/
│  ├─ index.html / styles.css / app.js / mark.svg
├─ tests/
│  ├─ test_services.py / test_api.py / test_boundaries.py
│  └─ synthetic_samples.py
└─ docs/
   ├─ IMPLEMENTATION_PLAN.md / DEMO.md / VERIFICATION.md
   └─ SOURCE_BUNDLE.md           # 完整代码合并文档
```

代码与样例均匿名化，无真实学校、身份或参赛者信息。`.env`、`.venv`、模型权重、运行缓存不包含在源码交付包内。

## 岗位审核

普通用户提交和修改岗位后进入待审核，仅本人可在“我的岗位提交”查看。管理员在独立后台“岗位审核与维护”中查看完整描述、通过或填写原因拒绝；通过后才进入公开岗位列表。审核只表示允许展示，不代表真实性担保。管理员直接发布的岗位即时展示。旧版数据库自动为管理员岗位保留展示，普通用户岗位转入待审核，不删除原有记录。

## 动态职业成长星图

技能树已升级为深色星图：正式模式由AI根据岗位、JD和缺口动态生成共享技能及职业方向；只有演示模式预置九方向。通过节点考核（至少3题、正确率80%、前置已完成）才记录完成，职业面板显示依赖闭包上的技能覆盖率，不提供录用概率。旧自记进度保留，新考核进度独立保存。演示加载/重置只影响页面内存。详见 [星图说明](docs/STARMAP.md)。
