# 本地 OCR 部署记录

部署日期：2026-11-04。

## 已完成

- 项目独立 `.venv`：Python 3.12、PaddlePaddle 3.2.2、PaddleOCR 3.3.2、PaddleX 3.3.13。
- `models/PP-OCRv5_mobile_det_infer/`：本地文字检测模型。
- `models/PP-OCRv5_mobile_rec_infer/`：本地中英文文字识别模型。
- `.env` 已写入上述目录；未修改其他模型配置，无需 OCR API 密钥。
- PaddleOCR 只接收内存 ndarray；不访问材料链接；禁用附加预处理模型与模型源联网检查。
- 运行库缓存定向至项目 `.runtime-cache/`，不保存用户原始材料。
- 平台已使用该项目环境重启至 `http://127.0.0.1:5088/`。

## 真实测试

直接推理测试禁止所有外网 socket 连接，以下三份合成样例均识别成功：

| 材料 | 行数 | 直接推理耗时 | 通过真实上传接口耗时 |
|---|---:|---:|---:|
| 招聘 PNG | 4 | 约3.35秒，含初始化 | 约3.31秒，含初始化 |
| 简历 PNG | 10 | 约0.86秒 | 约0.83秒 |
| 简历 PDF | 10 | 约1.78秒 | 约1.67秒 |

耗时仅代表本机本次合成资料，不是性能保证；首次启动通常包含模型初始化。

两份简历均命中手机号、身份证、邮箱、银行卡、住址、紧急联系人6类字段；脱敏导出接口返回200，完整合成手机号不出现在导出结果。招聘风险分析接口返回100规则分（非诈骗概率）。测试会话已清空。

全套单元/接口测试：**33 passed**；`pip check`：无依赖冲突。环境完整版本见 `requirements-ocr-tested.txt`。

## 使用

刷新平台后，到“材料解析”选择“个人简历”，上传 `docs/samples/resume.png` 或 `resume.pdf`。页面来源应显示 **PaddleOCR**，而不是“文字材料”。随后进入“隐私保护”选择该材料并检测。

关闭服务后可双击 `start.bat` 重启，或在项目目录运行：

```powershell
.\.venv\Scripts\python.exe run.py
```

模型与 `.env` 留在当前设备。源码压缩包不包含虚拟环境、模型权重与缓存；迁移到其他设备仍需按 README 准备这些内容。

官方模型来源：[PaddleOCR 模型说明与下载表](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html)。下载由部署步骤完成，应用运行期间不包含模型下载功能。

本记录描述OCR部署。后续已接入DeepSeek；大语言模型来源仍独立显示，详见DEEPSEEK_SETUP.md，未配置或不可用时降级为规则/检索模式。
