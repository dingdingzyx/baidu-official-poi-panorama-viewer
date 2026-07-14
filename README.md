# Baidu Official POI Panorama Viewer

[![CI](https://github.com/dingdingzyx/baidu-official-poi-panorama-viewer/actions/workflows/ci.yml/badge.svg)](https://github.com/dingdingzyx/baidu-official-poi-panorama-viewer/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)

一个只监听本机回环地址的交互式查看器：通过百度地图开放平台的官方地点检索 API 搜索 POI，并在用户显式选择某个 POI 后，使用官方 JavaScript API 展示该地点可用的全景。

English: a loopback-only interactive viewer built on documented Baidu Map Place and JavaScript Panorama APIs. It is not a crawler, a batch downloader, or a panorama-ID export tool.

## 公开版边界

- 只请求文档化的官方接口；没有页面抓取、并发扫描、代理、重试风暴或城市级批量任务。
- 没有 CSV/TXT 下载、历史结果库、断点续跑、`panoid` 显示或 `panoid` 导出。全景 ID 仅在浏览器中的官方 SDK 内部用于当前画面展示。
- 一次查询只接受一个城市和一个关键词。用户点击“下一页”才请求下一页，不后台预取、不自动换词、不自动遍历城市。
- 本项目不能也不会声称检索了一个城市的全部 POI 或全部全景。官方地点检索是排序检索，结果覆盖、权限、配额和全景可用性均由百度服务决定。
- 代码采用 MIT License；第三方地图数据、图像和 API 服务仍受其各自条款、权限和配额约束。

请在部署或使用前阅读当前的[百度地图开放平台服务条款](https://lbsyun.baidu.com/docs/pcsa?title=law%2Fopen%2Flaw)和[百度地图用户服务条款](https://map.baidu.com/zt/client/service/index.html)。本项目的设计目标是把公开代码限制在官方 API 的展示边界内，但它不能替代你的账号授权、合同条款或法律判断。

## 获取两个 AK

需要两个不同应用类型的 AK，二者都不要提交到 GitHub。

### 1. Server AK：官方地点检索

1. 登录[百度地图开放平台控制台](https://lbsyun.baidu.com/)，新建 **Server** 类型应用。
2. 在控制台开通地点检索对应服务，并创建/获取 Server AK。
3. IP 白名单填写运行本程序设备或服务器的**实际公网出口 IP**。本机开发在路由器/NAT 后时，填写的是路由器对外的公网 IP，不是 `127.0.0.1`。
4. 仅用于临时排障时可按百度控制台提示放宽白名单；排障结束后必须恢复为准确的公网 IP 或受控网段。不要把 Server AK 写进浏览器代码、截图、Issue 或仓库。

常见 `210` 表示当前公网出口 IP 没有匹配 Server AK 白名单。

### 2. Browser AK：官方 JavaScript API

1. 新建 **Browser** 类型应用，开通 JavaScript API。
2. 本机运行时 Referer 白名单填写 `127.0.0.1,localhost`。部署到网站后，改为实际受控域名，例如 `viewer.example.com`。
3. 不要在生产环境使用 `*`，也不要把 Server AK 当作 Browser AK 使用。
4. JavaScript API 全景属于高级权限。按[官方全景文档](https://lbsyun.baidu.com/docs/jsapi?title=jspopular3.0%2Fguide%2Fpanorama)联系百度开通试用或正式权限；只有普通 JSAPI 权限时，地图可加载，但全景不一定可展示。

常见 `220` 表示 Browser AK 的 Referer 白名单未匹配页面来源。官方文档也说明 `203` 通常是 AK 应用类型错误、`240` 是服务未开通或无权限、`302` 是配额耗尽、`401` 是官方并发限制。

## 配置与启动

要求 Python 3.10+。

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python wmx.py
```

在 `.env` 中填写两个 AK。程序打开 `http://127.0.0.1:8765/`，该服务不会监听局域网或公网地址。

```powershell
# 只检查是否配置，输出不会包含 AK 值
python wmx.py --check-config

# 使用其他本机端口
python wmx.py --port 8766
```

也可安装为命令：

```powershell
python -m pip install .
baidu-poi-panorama-viewer
```

## 配额与速度

| 行为 | 保护措施 |
| --- | --- |
| 地点检索 | 官方接口单页最多 20 条；本工具一组城市/关键词最多 5 页，即最多 100 条展示结果。 |
| 翻页 | 仅在用户点击“下一页”时发起一条新的官方请求。第 1 页之后的结果不会被自动丢弃，也不会被后台预取。 |
| 并发 | Python 端固定串行发送官方 Place API 请求，不提供 400/800/1000 并发模式。 |
| 日预算 | 默认本地保护为地点 4500 次、全景 100 次/日，只保存日期和计数，不保存 POI 或全景 ID。额度以你的官方控制台和合同为准；不要将本地值设置高于获授权额度。 |
| 全景 | 只有点击“查看全景”才申请一次本地展示许可并调用 Browser AK 对应的官方 SDK。 |

“100 条”是一次交互查询的展示上限，不是城市导出上限，更不是全量保证。这样可以避免把个人账号日配额耗在隐式批量枚举上，同时仍允许用户按需要显式翻页和发起新的关键词查询。

地点检索参数和每页上限以[官方 Place API 文档](https://lbsyun.baidu.com/docs/webapi?title=placev3%2Fguide%2Fwebservice-placeapiV3%2FinterfaceDocumentV2)为准。官方 Place API FAQ 也说明 POI 数据不保证实时或完整，因此没有合规方式用本工具证明“某城市 100% 全量”。

## 安全与隐私

- Server AK 只保存在 Python 进程内并只发送给固定的 `https://api.map.baidu.com/place/v2/search` 端点；不会发送给浏览器或写入日志。
- Browser AK 必然会随浏览器地图脚本使用，其安全边界是 Referer 白名单；仍应最小化白名单并定期轮换。
- HTTP 服务固定绑定 `127.0.0.1`，POST 请求要求 `Origin` 与当前回环 Host/端口完全一致；没有 CORS、下载、文件浏览或任意 URL 请求接口。
- 界面会提示：每次查询会按操作把城市、关键词和所选地点发送至百度地图开放平台；本程序仅保存本地请求计数，不保存地点或全景结果。
- 本地使用账本仅记录日期与请求次数，路径默认为 `.official-viewer/`，并被 Git 忽略。
- 同一用量目录一次只允许一个查看器进程，避免多进程意外绕过本地日预算；异常终止遗留的锁仅会在记录进程已不存在时自动回收。
- 发现安全问题请阅读 [SECURITY.md](SECURITY.md)，不要在公开 Issue 中发布 AK、日志、完整 API 响应或地址数据。

## 项目结构

```text
official_viewer/
  config.py       Safe .env loading and public-safe configuration
  quota.py        Counter-only local daily budget guard
  place_api.py    One-at-a-time documented Place API client
  server.py       Loopback-only local server and fixed routes
  static/         Browser UI and official JavaScript SDK integration
official_tests/   Offline unit and integration tests
docs/             Architecture and data-boundary notes
wmx.py            Compatible executable entry point
```

## 开发验证

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check wmx.py official_viewer official_tests
python -m ruff format --check wmx.py official_viewer official_tests
python -m unittest discover -s official_tests -v
python -m build
```

测试不调用真实百度服务，也不需要 AK。真实服务验证必须由 AK 所有者在已配置白名单和高级全景权限的环境中进行；未满足这些前置条件时，不能据此声称线上全景已验证。

## 贡献与版本

贡献规则见 [CONTRIBUTING.md](CONTRIBUTING.md)，变更记录见 [CHANGELOG.md](CHANGELOG.md)。请不要提交密钥、POI 批量结果、全景 ID、缓存、截图中的密钥或绕过官方配额/权限的代码。

## 致谢

谨以此项目致敬我最好的兄弟34那洁白无暇的爱情。

## License

本项目代码以 [MIT License](LICENSE) 发布。MIT License 不授予百度地图数据、图像或服务的额外权利。
