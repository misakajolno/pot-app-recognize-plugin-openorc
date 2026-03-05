# Pot-App OpenOCR 插件（OpenOCR Python Bridge）

这个仓库是一个新的 Pot OCR 插件项目，目标是把 [OpenOCR](https://github.com/Topdu/OpenOCR) 接入 Pot 的 `recognize` 插件接口。

## 插件定位

- 插件类型：`recognize`
- 运行方式：Pot 调用 `main.js` -> `main.js` 调 Python 桥接脚本 -> 桥接脚本调用 `openocr-python`
- 当前支持任务：`ocr`、`unirec`

## 目录结构

```text
pot-app-recognize-plugin-openorc/
├── info.json
├── main.js
├── openorc.png
├── scripts/
│   ├── openorc_bridge.py
│   └── package.ps1
└── README.md
```

## 先决条件

1. 安装 Python 3.9+。
2. 安装 OpenOCR：

```bash
pip install openocr-python==0.1.5
```

3. 可选：`server + torch` 模式需要额外安装：

```bash
pip install torch torchvision
```

## Pot 配置

安装 `.potext` 后，在 Pot 的 OCR 服务配置里填写：

- `Python Command`: 例如 `python`（或你的 Python 绝对路径）
- `Bridge Script Path`: 默认可留空，插件会自动尝试：
  - `插件目录/scripts/openorc_bridge.py`
  - `插件目录/openorc_bridge.py`
- `OpenOCR Task`: `ocr`（通用文本）或 `unirec`（文本/公式混合）
- `OpenOCR Mode`: `mobile` 或 `server`
- `OpenOCR Backend`: `onnx` 或 `torch`
- `Merge Lines`: 是否把识别行合并为一个文本结果
- `Timeout (ms)`: 默认 `180000`（首次下载模型更稳）
- 也可以直接按默认清单填写：`DEFAULT_CONFIG.md`

## 打包插件

```powershell
pwsh ./scripts/package.ps1
```

默认输出：

```text
dist/plugin.com.pot-app.openorc.potext
```

## 开发说明

- `main.js` 只做 Pot 侧参数适配、超时与错误处理。
- `scripts/openorc_bridge.py` 负责调用 OpenOCR 并规整输出。
- 插件读取 Pot 的截图缓存路径：`{cacheDir}/pot_screenshot_cut.png`。
