# OpenORC 默认配置导入清单（Pot）

> 目标：安装插件后，按下表填写即可直接使用。

## 推荐默认值（稳妥）

| 配置项 | 推荐值 | 说明 |
|---|---|---|
| Python Command | `C:/Users/Citlali/AppData/Local/Programs/Python/Python314/python.exe` | 建议用绝对路径避免 PATH 问题 |
| Bridge Script Path | 留空 | 留空时自动使用插件内置 `scripts/openorc_bridge.py` |
| OpenOCR Task | `ocr` | 截图文字识别常规场景推荐 |
| OpenOCR Mode | `mobile` | 启动快，资源占用低 |
| OpenOCR Backend | `onnx` | 与默认安装最兼容 |
| Merge Lines | `true` | 返回单段文本，适合翻译链路 |
| Timeout (ms) | `180000` | 首次模型下载可避免超时 |

## 备用配置（精度优先）

| 配置项 | 备用值 | 说明 |
|---|---|---|
| OpenOCR Mode | `server` | 更高精度，速度更慢 |
| OpenOCR Backend | `torch` | 需额外安装 `torch torchvision` |
| Merge Lines | `false` | 保留原始换行 |

## 首次使用检查清单

1. `python -X utf8 -m pip show openocr-python` 有输出版本号（应为 `0.1.5`）。
2. Pot 安装插件包：`.tmp/dist/plugin.com.pot-app.openorc.potext`。
3. 首次 OCR 会下载模型到：`C:/Users/Citlali/.cache/openocr/`。
4. 首次识别可能较慢，等待 10~60 秒属于正常。

