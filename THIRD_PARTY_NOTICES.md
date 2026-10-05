# 第三方组件与许可

本项目**不包含**任何第三方项目的源码副本（反编译内核通过 `fetch_engine.py` 从官方 release 下载），
但构建产物（`dist/WxapkgTool.exe`）会把它一并打包。发布二进制时需要保留下列声明。

| 组件 | 版本 | 许可 | 用途 | 说明 |
|---|---|---|---|---|
| [KillWxapkg](https://github.com/Ackites/KillWxapkg) | v2.4.1 | **MIT** | 反编译内核 | 官方 windows/amd64 版，UPX 压缩，37 MB。`fetch_engine.py` 会校验 MD5 `5593a83f60f742bfb27c4fef756dfae7` |
| [Qt for Python / PySide6-Essentials](https://doc.qt.io/qtforpython/) | 6.11.2 | **LGPL-3.0** | 图形界面 | 动态链接 Qt 库 |
| [PyInstaller](https://pyinstaller.org/) | 6.22.3 | GPL-2.0-or-later **+ 打包例外条款** | 打包成单文件 exe | 例外条款允许打包闭源/其它许可的软件 |

## 关于 PySide6 (LGPL-3.0)

打包分发的 exe 内嵌了 Qt 库。LGPL-3.0 的要求是：接收方能够替换其中的 Qt 部分。

- Qt / PySide6 的完整对应源码可从 <https://download.qt.io/> 与 <https://pypi.org/project/PySide6-Essentials/> 获取。
- 若要重新链接：用 `python build.py --onedir` 构建目录版，替换 `_internal/` 下的 Qt DLL，
  或用 `pip install PySide6-Essentials==6.11.2` 后自行打包，即可生成功能等价的替代品。
- 本项目自身代码（`app/`、`build.py`、`make_icons.py`）以 MIT 授权，见 `LICENSE`。

## 关于 KillWxapkg

MIT 许可，可自由分发，需保留其版权声明。原作者仓库：<https://github.com/Ackites/KillWxapkg>。

本项目只是给它套了一层 Windows GUI 并做了打包与流程编排（分包处理、源码修复、转 uni-app、敏感信息报告收口），
**反编译能力本身完全来自 KillWxapkg**。
