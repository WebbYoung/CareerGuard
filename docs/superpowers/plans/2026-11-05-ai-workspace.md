# AI求职工作空间扩展实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and independent subsystem delegation under dispatching-parallel-agents.

**Goal:** 新增启发式AI简历/Word导出/证件照、通用模型与Embedding RAG、受控小安助手、企业入驻与岗位发布。
**Architecture:** 现有FastAPI+原生前端+SQLite上新增独立路由与视图；模型网关统一OpenAI兼容/Anthropic/Ollama。SQLite持久化向量、企业审核、加密简历与对话；只在显式操作时调用已配置模型。
**Tech Stack:** Python、SQLite、python-docx、Canvas/Three.js与原生JS。
**Spec:** 用户本次明确要求，并已明确授权自行决定，不再询问或请求许可。

## Global Constraints
- 配置前不测试真实对话、图片或Embedding接口；所有测试阻止网络，使用合成数据/模拟传输。
- 模型密钥服务端加密，保存配置与启动状态不探测模型。
- 无任意网页抓取、重定向或返回图片URL自动下载；用户原自拍仅在内存处理。
- 新增所有数据按当前Session账号隔离，写入沿用CSRF与数据代数保护。
- 小安工具白名单仅自我资料、公开审核岗位、知识库、导航和表单提案，不执行任意代码/删除/管理操作。
- 企业资料审核不是工商真实性认证；公司通过资料审核且岗位通过内容审核后公开。

## Independent Ownership
- Provider/RAG：model_gateway/model_schema/rag/model_api与管理端模型组件。
- Resume/photo：resume_api/resume_builder/resume_schema/resume-studio组件。
- Company：company_api/company_schema/company页面与管理员审核组件。
- Root：助手API/工具/弹窗、共享路由schema与权限整合、入口/机器人/管理员集成。

## Review Focus
- 不发生任何真实模型/向量测试或隐式探测。
- 企业不能通过通用岗位接口绕过机构审核和归属。
- 工具参数与模型输出不变成SQL、CSS选择器、HTML或URL执行。
- 删除个人数据包括新增简历/图片和助手历史，异步写回不能复活已删除内容。
- Word包含真实草稿与处理后照片；AI不虚构学校/公司/成果，未配置模型明确说明。
- 企业执照和原自拍上传大小/类型校验，原始文件不落磁盘。

### Tasks
- [x] Provider/RAG/embedding/image settings + offline tests.
- [x] Resume conversation + grounded polish + DOCX/photo + offline tests.
- [x] Enterprise registration/license/company jobs/admin review + offline tests.
- [x] Assistant safe tool loop + chat UI + robot guidance/form actions.
- [x] Shared schema/router/nav/role/data-wipe integration.
- [x] Whole offline suite and real browser manual flows without model calls; review/fix.
- [x] Docs, source archive, secret scan and local version history.
