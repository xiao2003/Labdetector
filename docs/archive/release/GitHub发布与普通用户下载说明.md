# GitHub 发布与普通用户下载说明

版本：1.0.0

## 当前正式 GitHub Release 附件

当前正式 Release 对应的下载文件为：

1. `NeuroLab-Hub-Setup-v1.0.0.exe`
2. `NeuroLab_Hub_1.0.0.zip`
3. `NeuroLab_Hub_1.0.0_fresh_validation.zip`

说明：
- 第一项为带安装界面的标准安装包。
- 第二项为标准便携交付包。
- 第三项为包含新机复验口径的复验包。
- 三个文件都基于 `1.0.0` 版本基线命名。

## 普通用户推荐下载项

普通用户推荐优先下载：

1. `NeuroLab-Hub-Setup-v1.0.0.exe`

适用场景：
- 需要标准安装界面
- 需要桌面快捷方式和开始菜单入口
- 不希望手动处理目录结构

便携部署、换机复验或内测场景推荐下载：

1. `NeuroLab_Hub_1.0.0.zip`

适用场景：
- 直接解压使用
- 启动 Windows 主程序
- 继续配置 Raspberry Pi 边缘节点

## 压缩包包含内容

当前标准发布压缩包应包含：

1. Windows 轻量启动入口
2. `_internal/` 运行目录
3. `APP/` 运行目录
4. `pi/` 目录
5. 必要说明文档

说明：程序入口文件名保留 `NeuroLab Hub` 简称，但项目正式名称统一为“NeuroLab Hub——可编排专家模型的实验室多模态智能中枢”。

## 发布说明

当前版本不再以 `onefile` 作为正式发布目标，正式推荐交付路径为：

- Windows：`SilentDir/onedir`
- Pi：复制 `pi/` 目录并执行一键配置或自治安装

## 配套文档

建议与 Release 一起查看：

1. `docs/release/NeuroLab_Hub_正式发布说明_1.0.0.md`
2. `docs/product/NeuroLab_Hub_用户手册.md`
3. `docs/product/NeuroLab_Hub_软件说明书.md`
4. `docs/release/NeuroLab_Hub_测试报告_1.0.0.md`
