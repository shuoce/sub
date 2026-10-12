# 🚀 硕策订阅中心

欢迎来到 **硕策订阅中心**

这里提供常用订阅地址，支持 NekoBox、Clash 等客户端使用。

---

# 📡 订阅地址

## 📱 NekoBox订阅

适用于：
- NekoBox
- v2rayN
- 其他支持 Base64/VLESS 订阅的客户端

订阅地址：

```
https://shuoce1.eu.cc/share/a.txt
```

---

## 🌐 Clash通用订阅

适用于：
- Clash Meta
- Mihomo
- 其他 Clash 内核客户端

订阅地址：

```

https://shuoce1.eu.cc/share/clash.yaml
```

---

## 📲 NekoBox临时分享订阅

临时节点分享使用：

```

https://shuoce1.eu.cc/share/mao
```

---

# 📖 使用教程

## NekoBox

1. 打开 NekoBox
2. 进入「订阅管理」
3. 点击添加订阅
4. 粘贴：

```

https://shuoce1.eu.cc/share/a.txt
```

5. 更新订阅即可


---

## Clash / Mihomo

1. 打开 Clash 客户端
2. 找到「配置 / Profiles」
3. 添加远程配置
4. 粘贴：

```

https://shuoce1.eu.cc/share/clash.yaml
```

5. 下载并启用配置


---

# 📁 文件结构

```
sub
├── .github/workflows/update-sub.yml   # CI：每 3 小时拉取 → 测活 → 发布
├── fetch_nodes.py                     # 流水线主程序（CI 执行）
├── local_probe.py                     # 白名单探测（本机执行，见白名单刷新手册.md）
├── nodes.txt                          # 上游原始节点快照（CI 生成）
├── nodes_new.txt                      # 过滤后节点（CI 生成）
├── sub.txt / clash.yaml               # 订阅产物（CI 生成）
├── index.html / CNAME / style.css     # Pages 站点
│
└── share
    ├── a.txt                          # NekoBox 订阅（= sub.txt，Base64）
    ├── clash.yaml                     # Clash 订阅
    ├── alive.txt                      # 存活白名单（本机探测生成，CI 不覆盖）
    ├── fixed.txt                       # 免检固定节点    ├── mao                            # 临时分享
    └── synchronous                    # 基础配置模板
```

---

# ⚡ 网站地址

主页：


https://shuoce1.eu.cc/


---

# 🔄 更新说明

- 订阅由 GitHub Actions 每 3 小时自动更新并发布，客户端刷新订阅即可获取最新节点
- `share/alive.txt` 白名单由本机手动刷新（换网络或节点异常时），见 [白名单刷新手册](白名单刷新手册.md)


---

# ⚠️ 注意事项

- 请勿滥用节点资源
- 请遵守当地法律法规
- 订阅内容仅供个人使用


---

© 2026 shuoce
