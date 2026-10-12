
<p align="center">
  <img src="https://img.baidu.re/i/2026/10/n5mccf.jpg" width="88" height="88" alt="硕策 Logo">
</p>

<h1 align="center">硕策订阅中心</h1>

<p align="center">
  <strong>SHUOCE SUBSCRIPTION</strong>
</p>

<p align="center">
  简洁 · 自动更新 · 持续维护
</p>

<p align="center">
  个人维护的订阅配置与节点管理项目。
</p>

<p align="center">
  <a href="https://shuoce1.eu.cc/">
    <img src="https://img.shields.io/badge/在线访问-1683ff?style=for-the-badge" alt="在线访问">
  </a>
  <a href="https://github.com/shuoce/sub">
    <img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github" alt="GitHub">
  </a>
  <a href="https://github.com/shuoce/sub/issues">
    <img src="https://img.shields.io/badge/问题反馈-22c55e?style=for-the-badge" alt="问题反馈">
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Project-Shuoce%20Sub-1683ff?style=flat-square">
  <img src="https://img.shields.io/badge/Automation-GitHub%20Actions-6366f1?style=flat-square">
  <img src="https://img.shields.io/badge/Status-Maintained-22c55e?style=flat-square">
</p>

---

## ✦ 关于项目

**硕策订阅中心（Shuoce Subscription）** 是一个由个人维护的订阅配置与节点管理项目。

项目通过自动化工作流整理和更新订阅文件，并提供相应的配置入口，方便日常管理与使用。

项目以实用、轻量、易维护为主要目标，并根据实际运行情况持续调整。

> 让配置管理更简单。

---

## 📡 订阅入口

根据所使用的客户端，选择对应的订阅地址。

### 01 · 通用订阅

适用于支持相应订阅格式的客户端，例如 NekoBox、v2rayN 等。

**订阅地址：**

```text
https://shuoce1.eu.cc/share/a.txt
```

### 02 · Clash / Mihomo 订阅

适用于支持 Clash 配置格式的客户端，例如 Clash Meta、Mihomo 等。

**订阅地址：**

```text
https://shuoce1.eu.cc/share/clash.yaml
```

### 03 · 临时分享入口

用于临时分享场景。

**访问地址：**

```text
https://shuoce1.eu.cc/share/mao
```

---

## 📖 使用教程

### NekoBox

1. 打开客户端，进入订阅管理页面。
2. 选择添加订阅。
3. 粘贴通用订阅地址。
4. 保存订阅并执行更新。
5. 根据客户端提示完成配置。

### Clash / Mihomo

1. 打开对应客户端。
2. 进入配置或 Profiles 页面。
3. 选择添加远程配置。
4. 粘贴 Clash 订阅地址。
5. 下载配置并按客户端提示启用。

不同客户端的菜单名称可能略有区别，请以实际界面为准。

---

## ⚡ 自动更新

项目通过 GitHub Actions 自动执行订阅处理流程。

- **定时执行：** 按工作流配置定期运行。
- **节点处理：** 获取数据并执行相应的过滤与检测流程。
- **文件生成：** 更新相应的订阅文件。
- **客户端同步：** 客户端刷新订阅后获取最新配置。

部分白名单文件由本机手动维护，具体规则请参阅 [白名单刷新手册](./白名单刷新手册.md)。

---

## 📁 项目结构

```text
sub/
├── .github/
│   └── workflows/
│       └── update-sub.yml
├── fetch_nodes.py
├── local_probe.py
├── nodes.txt
├── nodes_new.txt
├── sub.txt
├── clash.yaml
├── index.html
├── CNAME
├── style.css
├── 白名单刷新手册.md
└── share/
    ├── a.txt
    ├── clash.yaml
    ├── alive.txt
    ├── fixed.txt
    ├── mao
    └── synchronous
```

以上为项目文件结构示意，具体文件以仓库实际内容为准。

---

## 🌐 在线访问

<p align="center">
  <a href="https://shuoce1.eu.cc/">
    <img src="https://img.shields.io/badge/立即访问_硕策订阅中心-1683ff?style=for-the-badge" alt="立即访问">
  </a>
</p>

<p align="center">
  <a href="https://shuoce1.eu.cc/">
    <strong>https://shuoce1.eu.cc/</strong>
  </a>
</p>

通过浏览器即可访问项目主页。订阅文件的可用性取决于服务状态与网络环境。

---

## ✨ 项目特点

| 特点 | 说明 |
|---|---|
| 🚀 自动化 | 通过 GitHub Actions 执行更新任务 |
| 📡 多格式 | 提供通用订阅与 Clash 配置 |
| 🧩 模块化 | 区分数据处理、订阅产物与站点文件 |
| 🛠️ 易维护 | 支持节点检测与白名单管理 |
| 🔄 持续更新 | 根据实际运行情况持续优化 |

---

## 🛠️ 技术栈

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white" alt="HTML5">
  <img src="https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white" alt="CSS3">
  <img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" alt="GitHub Actions">
</p>

项目涉及的具体技术与运行方式，以仓库中的实际代码和工作流配置为准。

---

## 🔄 维护计划

项目将根据实际使用情况持续维护：

- 自动更新流程优化
- 订阅文件异常排查
- 节点检测与白名单维护
- 站点展示与访问体验优化
- 配置文件结构整理
- 稳定性与兼容性改进

具体更新以仓库提交和实际发布内容为准。

---

## 👤 关于 Shuoce

<p align="center">
  <img src="https://img.baidu.re/i/2026/10/n5mccf.jpg" width="64" height="64" alt="Shuoce">
</p>

<p align="center">
  <strong>硕策 · Shuoce</strong>
</p>

<p align="center">
  Personal Project · Independently Maintained
</p>

本项目由个人独立维护，主要用于个人项目实践与日常配置管理。

---

## ⚠️ 使用须知

- 请合理使用相关资源，遵守适用的法律法规。
- 请妥善保管个人配置与相关访问信息。
- 服务可用性受网络环境、上游数据及托管服务状态影响。
- 项目中涉及的第三方资源，其版权归原作者或相关权利人所有。
- 具体使用方式请以仓库实际发布的文件和说明为准。

---

## 💬 反馈

如发现项目文件异常、自动更新失败或有改进建议，可通过 GitHub Issues 反馈。

<p align="center">
  <a href="https://github.com/shuoce/sub/issues">
    <img src="https://img.shields.io/badge/提交反馈-1683ff?style=for-the-badge" alt="提交反馈">
  </a>
</p>

---

<p align="center">
  <a href="https://shuoce1.eu.cc/">🌐 在线主页</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/shuoce/sub">📦 GitHub 仓库</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/shuoce/sub/issues">💬 Issues</a>
</p>

<p align="center">
  <sub>© 2026 Shuoce · SHUOCE SUBSCRIPTION</sub>
</p>
