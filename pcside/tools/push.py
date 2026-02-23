#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push.py - 终极安全一键推送脚本 (自动代理重试版)
"""
import os
import subprocess
import sys
import time

# ==========================================
# ★ 核心配置：你的代理端口 ★
# ==========================================
DEFAULT_PROXY_PORT = "7890"

# 获取项目根目录，确保 git 命令在正确的位置执行
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
os.chdir(project_root)


def run_cmd(cmd, show_output=True, ignore_error=False):
    """执行 Shell 命令的包裹函数"""
    try:
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True, encoding='utf-8', errors='ignore')
        if result.returncode != 0 and not ignore_error:
            return False, result.stderr.strip()
        if show_output and result.stdout.strip():
            print(result.stdout.strip())
        return True, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def check_and_fix_gitignore():
    """强制检查并修复 .gitignore，防止把模型和日志推送到 GitHub 导致崩溃"""
    gitignore_path = os.path.join(project_root, ".gitignore")
    essential_rules = [
        "__pycache__/", "*.py[cod]", "*$py.class", "models/", "pcside/log/",
        "pcside/knowledge_base/faiss_index/", "pcside/knowledge_base/docs/*.txt"
    ]

    existing_rules = []
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            existing_rules = [line.strip() for line in f.readlines()]

    missing_rules = [rule for rule in essential_rules if rule not in existing_rules]

    if missing_rules:
        print("🛡️ 检测到缺失的安全屏蔽规则，正在自动修复 .gitignore ...")
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write("\n# 自动生成的安全屏蔽规则\n")
            for rule in missing_rules:
                f.write(f"{rule}\n")

        # 将已加入缓存的非必要文件移出暂存区
        run_cmd(
            "git rm -r --cached models/ pcside/log/ pcside/knowledge_base/faiss_index/ pcside/knowledge_base/docs/ __pycache__/",
            show_output=False, ignore_error=True)


def set_proxy(port):
    """设置 Git 全局代理"""
    proxy_url = f"http://127.0.0.1:{port}"
    print(f"⚙️ 正在开启 Git 代理: {proxy_url}")
    run_cmd(f"git config --global http.proxy {proxy_url}")
    run_cmd(f"git config --global https.proxy {proxy_url}")


def unset_proxy():
    """清除 Git 全局代理"""
    print("🧹 正在清理代理设置...")
    run_cmd("git config --global --unset http.proxy", show_output=False, ignore_error=True)
    run_cmd("git config --global --unset https.proxy", show_output=False, ignore_error=True)


def main():
    print("=" * 60)
    print("🚀 LabDetector 项目自动代理推送工具")
    print("=" * 60)

    # 1. 安全检查
    check_and_fix_gitignore()

    # 2. 获取当前状态
    success, status_out = run_cmd("git status -s", show_output=False)
    if not status_out:
        print("✅ 当前工作区很干净，没有需要提交的代码。")
        return

    print("📋 待提交的更改：")
    print(status_out)

    # 3. 询问提交信息
    commit_msg = input("\n💬 请输入本次更新说明 (直接回车默认: 'Auto update'): ").strip()
    if not commit_msg:
        commit_msg = f"Auto update: {time.strftime('%Y-%m-%d %H:%M')}"

    # 4. 执行 Git 工作流
    print("\n⏳ 1/4 正在添加文件...")
    run_cmd("git add .")

    print("⏳ 2/4 正在提交更改...")
    run_cmd(f'git commit -m "{commit_msg}"', show_output=False)

    print("⏳ 3/4 正在拉取远程代码...")
    # 尝试不带代理拉取一次
    success, err = run_cmd("git pull origin master --no-edit", ignore_error=True)
    if not success and ("443" in err or "reset" in err or "Timed out" in err):
        print("🌐 检测到网络连接困难，尝试启用代理...")
        set_proxy(DEFAULT_PROXY_PORT)
        run_cmd("git pull origin master --no-edit")

    print("⏳ 4/4 正在推送到 GitHub...")
    success, err = run_cmd("git push origin master")

    # 5. 错误处理与代理重试
    if not success:
        if "443" in err or "reset" in err or "Timed out" in err:
            print(f"🌐 推送失败，正在尝试通过端口 {DEFAULT_PROXY_PORT} 自动重试...")
            set_proxy(DEFAULT_PROXY_PORT)
            retry_success, retry_err = run_cmd("git push origin master")
            if retry_success:
                print("\n🎉 代理穿透成功！代码已同步至 GitHub。")
            else:
                print(f"\n❌ 推送依然失败，请确认代理软件是否开启且端口正确：\n{retry_err}")
        else:
            print(f"\n❌ 遇到非网络错误：\n{err}")
    else:
        print("\n🎉 推送成功！")

    # 始终清理代理环境
    unset_proxy()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消操作。")
        unset_proxy()
