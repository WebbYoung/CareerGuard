# 本机摄像头画面辅助

2026-11-05。用于用户自己的AI面试练习，检测入镜与几何姿态，独立于考试判分、AI文字建议及招聘判断。

## 模型选择与本机部署

采用MediaPipe Face Landmarker和Hand Landmarker。前者给出脸部关键点和几何变换矩阵，后者给出手部关键点，直接服务于本功能需要的朝向、位置与位移计算。未建立身份人脸库，不生成表情、情绪、注意力、诚信或录用判断。

本项目`.venv`已安装MediaPipe 1.2.2，本地模型已放在`models/vision/face_landmarker.task`与`models/vision/hand_landmarker.task`。CPU推理，不需要GPU。Windows中文目录采用Python读取模型字节再交给原生运行时，避免原生库无法打开中文路径的问题。

换机安装：

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-vision.txt
```

将单独的`career-guard-vision-models.zip`解压到项目根目录，保留`models/vision`层级，再按原方式启动。程序运行时不自动下载模型，不从用户输入读取模型URL。

官方依据：[Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker)、[Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)、[MediaPipe PyPI](https://pypi.org/project/mediapipe/)。

模型来源与SHA256：

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| face_landmarker.task | 3758596 | 64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff |
| hand_landmarker.task | 7819105 | fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1 |

官方模型包：[人脸任务包](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task)、[手部任务包](https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task)。上表记录本次实际下载内容，源站latest后续可能变更。

## 使用流程

进入「AI面试」，在镜头辅助工具栏勾选本机画面分析，点击开启摄像头。浏览器可能弹出设备权限请求。坐在明亮环境，单人入镜，正对镜头，点击校准，再开始或继续AI面试。镜头以可拖动的小窗持续显示：桌面宽244px，窄屏宽184px。绿色边框表示稳定，黄色表示观察中，橙红色表示需要调整，并配合节流后的弹窗提醒。前台不显示左右、上下、倾斜角度数字或关键点线条。灵敏度收进设置，支持宽松、标准、严格三档，需关闭后切换。小窗支持拖动、方向键移动和Home复位，关闭小窗即停止设备。

标准模式对左右偏转超过25°、上下偏转超过25°、倾斜超过20°且持续约2秒的情况给出提醒。校准用于修正小范围安装角度偏差，明显侧头时拒绝校准。位移以人脸宽度归一化，不是精确医学角度测量。

提醒覆盖：人脸缺失、多张人脸、偏离中央、距离过近/过远、持续偏头、头部画面位移、手部进入脸部画面区域、连续手部关键点位移。正常眨眼与说话不属于检查项。没有可靠检测到手部时明确提示无法判断，不能把“未检测到手”当成“没有动作”。

这是一项练习辅助。软件不能阻止身体动作，也不能可靠识别所有“小动作”。自然手势、不同身体条件、光线、遮挡和摄像头移动都可能影响结果。提醒不扣面试分，不自动认定作弊，不改变用户求职或招聘资格。

## 数据与会话安全

浏览器只请求视频，不附带音频。视频流在本页显示，以约2–3帧/秒采样JPEG，通过已认证同源请求发送到本机Python服务，最长边约640像素。接口严格限制JPEG签名、字节大小及解码像素，不使用磁盘临时上传文件。

图像不写入SQLite、材料表、审计正文或磁盘，也不加入DeepSeek对话。仅在内存保留最多4秒的坐标变化，单个账号最多一个活跃监测，总上限16个，停止后释放，60秒无请求过期。页面切换、后台隐藏、撤回同意、退出、结束面试及关闭页面都会停止设备轨道；权限请求迟到时也会释放新得到的轨道。

API需登录、CSRF与独立监测令牌，跨账号不能读取或结束他人的监测。模型采用无跟踪的单帧模式与串行锁，避免不同账号共享原生视频跟踪上下文。无身份识别、无画面录像、无姿态成绩数据库。

## 验证记录

80项Python自动测试和8项前端状态机测试通过。覆盖几何角度、防抖、手部位置/位移、无脸、多脸、非法图像、超限帧、访客拒绝、跨账号拒绝、停止后旧帧拒绝、未同意不申请设备、模型不可用、权限迟到与轨道释放。状态机测试使用设备替身，不代替真实硬件验收。

真实MediaPipe测试：公开测试人像识别1张脸；拼接测试图识别2张脸；官方双手图片识别2只手；空白图识别0张脸。CPU预热后人像约14毫秒、双手约23毫秒，本机测试数据，不是跨设备性能承诺。真实接口完成图像处理、校准、停止与无图片材料落库检查。

安装后重新实测PaddleOCR，招聘PNG、简历PNG/PDF均通过，简历保留6类隐私检测能力。

尚未对本机实体摄像头进行端到端拍摄测试。真实使用需用户主动授权设备，浏览器不支持、设备占用或权限拒绝时会说明原因，并可继续文字/语音面试。
