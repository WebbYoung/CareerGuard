# 职安全站视觉重设计

版本：v0.11.0，日期：2026-11-05。

依据用户批准的三张视觉稿进行组合：首页采用第一张沉浸大视觉，侧边栏与工作台采用第二张玻璃组件，技能树采用第三张立体星图材质。并非逐页复制Apple站点。

## 参考
- [Apple首页](https://www.apple.com/)
- [MacBook Pro产品详情](https://www.apple.com/macbook-pro/proled-xdr-display/)
- [iPhone分类页](https://www.apple.com/iphone/)
- [Vision Pro产品页](https://www.apple.com/apple-vision-pro/)
- [Apple商店](https://www.apple.com/store)

## 实现边界
- static/cinematic.css是公共视觉层，置于原有功能样式之后。
- static/cinematic.js只负责视口入场、装饰图轻量倾斜和首页入口；不读取材料或保存用户输入。
- static/assets包含为本项目生成的独立玻璃素材，不是Apple素材。
- 静态立体素材配合CSS过渡实现观感，不引入Three.js、外部CDN或新部署服务。
- 职业图谱的节点坐标、技能依赖、考试完成状态继续来自原有控制器及服务端；球体只更新内部样式。
- 减少动态时关闭位移与倾斜，降低透明度或高对比时改用实色材质。

## 验证
- 桌面逐页导航、390px下十个功能页无横向溢出。
- 登录页手机输入为16px；主页无JS依赖的真实链接仍可用。
- 首页AI面试入口到 /app#interview，等待账号与平台初始化后显示。
- 星图演示加载进度、职业聚焦、阶段展开、节点详情、适配全图正常。
- 现有88项Python测试与36项Node测试通过；新增入口初始化顺序及导航白名单测试。
- 此次未重新调用OCR或云端模型，不改变数据、权限或计分逻辑；未做真实移动设备测试。

## 预览
- cinematic-home.png：桌面首页（减少动态模式捕获完整页面）。
- cinematic-workbench.png：工作台。
- cinematic-starmap.png：星图与节点详情。
- cinematic-mobile.png：390px首页（减少动态模式捕获完整页面）。
