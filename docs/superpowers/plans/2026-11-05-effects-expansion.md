# 强化视觉特效实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 根据用户明确要求，默认全开毛玻璃、动态粒子、流星雨、炫光边缘、卡片反馈及统一玻璃小图标。
**Architecture:** effects-core.js提供纯粒子数学和可暂停的唯一帧循环，effects.js负责Canvas、原生特效选择器、卡片与图标渐进增强；effects.css提供静态毛玻璃材质和合成层动画。
**Tech Stack:** 原生JS/Canvas2D、CSS、独立玻璃图标图集。不引入jQuery/CDN，不更改业务服务。
**Spec:** 用户本次具体要求与参考仓库 https://github.com/sunyctf/js-effects 。

## Global Constraints
- 默认全开，提供轻量与关闭；减少动态设置和隐藏页面停止连续动画。
- 所有装饰层pointer-events:none，不遮挡表单、摄像头、图谱和考核按钮。
- 不变更账号、材料、权限或数据存储，不新增网络抓取到产品代码。
- 图标重绘保留原有无障碍名称；按钮仍有文字或aria-label。

## Review Focus
- 帧循环暂停、恢复、反复模式切换不得出现多重RAF。
- 粒子数、连线数、流星数与像素面积均有上限。
- MutationObserver不得因自建装饰不断重绘，移除节点应释放观察。
- 星图拖动时不叠加卡片倾斜；键盘操作没有位移动画。
- 深色毛玻璃背景中正文、警告和输入可读。

### Tasks
- [x] 纯核心及测试：预算、步进、连线去重与生命周期；先失败后实现。
- [x] Canvas星云粒子、鼠标连接、流星雨、点击微粒及极光光场。
- [x] 卡片环绕光带/呼吸光晕/聚光、展示卡片3D倾斜、按钮涟漪、图标统一。
- [x] 六个独立页面接入，手机、减少动态、隐藏暂停及业务交互验证。
- [x] 新鲜上下文审查；全部测试、截图、文档、打包与本地版本提交。

## Rulings
- 参考仓库效果类型与实现思路，使用有预算的原生模块重写，不复制650粒子/多重动画循环或引入jQuery。
- 连续装饰动画按用户明确意愿启用；保留系统减少动态与一键关闭能力。

## 审查与验证记录
- 新鲜上下文审查后的聚光裁剪、sticky面板、图标选择器与启动并发问题均已修复。
- 91项Python、46项Node测试通过；浏览器确认特效档位、减少动态、手机页面与十步引导/跳过/续接。
