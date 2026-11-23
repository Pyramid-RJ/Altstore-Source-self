# 自用 AltStore 源

个人的 AltStore / SideStore 源，只收录自己在用的应用。GitHub Actions 每 6 小时同步一次上游 Releases，无需人工维护。

## 收录的应用

| 应用 | 说明 | 仓库 |
| --- | --- | --- |
| **DSH Go** | DeepSeek Harness（dsh）手机客户端：手机上本机运行，也能遥控电脑上正在跑的会话 | [ccch1mneyyy/dsh-Go](https://github.com/ccch1mneyyy/dsh-Go) |
| **PiliPlus** | 使用 Flutter 开发的 BiliBili 第三方客户端（基于 pilipala / PiliPalaX） | [bggRGjQaUbCoE/PiliPlus](https://github.com/bggRGjQaUbCoE/PiliPlus) |

源内版本号由脚本自动生成，不在此手写，避免过期。

## 添加源

在 AltStore / SideStore 的 **Sources（源）** 页面点 `+`，填入以下任一地址：

```
https://raw.githubusercontent.com/Pyramid-RJ/Altstore-Source-self/main/generated/apps.json
```

```
https://raw.githubusercontent.com/Pyramid-RJ/Altstore-Source-self/main/alt_store.json
```

两个地址内容完全一致，只是文件名风格不同。

## 自动更新

- Actions 每 6 小时跑一次 `scripts/generate.py`：按 `apps/` 里每个应用的配置拉取上游 Releases，筛出 iOS 构建，更新源文件并以 `github-actions[bot]` 身份提交。
- 新增上游 Release 后，AltStore / SideStore 里会显示可更新，并产生一条 News 通知。
- 也可以手动触发：Actions → **Update Source** → Run workflow。

## 目录结构

```
source.json            源级信息（名称、标识、图标、tintColor、描述）
apps/                  每个应用一个配置文件，加应用只改这里
  dsh-go.json
  piliplus.json
scripts/generate.py    读上游 API 生成源文件（只用 Python 标准库）
assets/source-icon.png 源的图标
generated/apps.json    生成物，请勿手改
alt_store.json         同上，经典文件名的副本
```

## 新增一个应用

在 `apps/` 里放一个 JSON 文件，跑一次 `python scripts/generate.py` 确认输出，提交后 Actions 会接着维护。

主要字段：

| 字段 | 说明 |
| --- | --- |
| `repo` | 上游仓库，`owner/repo` |
| `assetPattern` | 匹配 ipa 资产名的正则，例如 `ios[^/]*\.ipa$` |
| `versionStripPrefix` | tag 前缀，例如 `v`（`v1.3.0` → `1.3.0`） |
| `buildVersionRegex` | 从资产名提取 `buildVersion`（ipa 的 CFBundleVersion），可选 |
| `notesFromAsset` | 从 Release 附带的小 JSON 取更新日志，可选 |
| `maxVersions` | 保留的版本数量上限 |
| `minOSVersion` | 最低系统版本 |
| `enabled` | 设为 `false` 可暂停收录 |

`name`、`bundleIdentifier`、`subtitle`、`iconURL`、`tintColor`、`category`、`screenshots`、`privacy` 等展示字段照 AltStore 源规范填写。

> 只要某个应用抓不到任何可用 Release，脚本会整轮失败并保留上一版文件 —— 不会因为上游抖动就把某个应用从源里删掉。

## 安装说明

源内收录的是上游发布的**未签名 ipa**，AltStore / SideStore 安装时会用你的 Apple ID 重签：

- 免费 Apple ID：证书 7 天有效，到期需在设备上用 AltStore 刷新；
- Apple Developer 账号，或 SideStore 配合脉冲 / 热刷新等方案可长期使用。
- 最低系统要求：DSH Go 与 PiliPlus 均为 **iOS 15.0**。

## 免责声明

本仓库只生成并托管指向上游 Releases 的索引信息，不修改、不重打包任何应用；所有资源版权归各应用作者所有（DSH Go 遵循 AGPL-3.0，PiliPlus 及其内容版权归其作者与哔哩哔哩）。请自行评估使用风险。
