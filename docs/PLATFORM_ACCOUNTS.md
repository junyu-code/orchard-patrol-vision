# 平台账号保存说明

本项目需要记录甲方平台入口，但账号密码不应提交到 GitHub。

## 平台入口

- 甲方A平台：`https://judaonongye.hhzzss.cn/index`
- 甲方B管理平台：`https://gl.xsjny.com/web/robot-analysis-ui/#/analytics`
- 甲方B大屏：`https://gl.xsjny.com/web/robot-data-view/index.html`

## 本地凭据

真实账号密码保存在：

```text
config/platform_accounts.local.json
```

该文件已加入 `.gitignore`，只在本机保存。

仓库中保留的模板文件是：

```text
config/platform_accounts.example.json
```

新机器部署时，复制模板为 `platform_accounts.local.json` 后填入真实账号密码即可。
