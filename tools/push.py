#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push.py - 终极安全一键推送脚本 (防大文件 + 自动网络重试版)
"""
import os
import subprocess
import sys
import time

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

        # 如果之前已经把错误文件加入 git 了，强行把它们移出暂存区
        run_cmd(
            "git rm -r --cached models/ pcside/log/ pcside/knowledge_base/faiss_index/ pcside/knowledge_base/docs/ __pycache__/",
            show_output=False, ignore_error=True)


def handle_network_failure():
    """网络失败时的代理设置向导"""
    print("\n" + "=" * 50)
    print("❌ 推送失败：网络连接被重置 (Connection was reset)")
    print("💡 这通常是因为国内访问 GitHub 受限。")
    choice = input("是否需要为您配置本地代理端口并重试？(输入端口号，如 7890，直接回车取消): ").strip()

    if choice and choice.isdigit():
        proxy_url = f"http://127.0.0.1:{choice}"
        print(f"⚙️ 正在设置全局 Git 代理: {proxy_url}")
        run_cmd(f"git config --global http.proxy {proxy_url}")
        run_cmd(f"git config --global https.proxy {proxy_url}")
        print("✅ 代理设置完成，正在重新尝试推送...")
        return True
    return False


def main():
    print("=" * 60)
    print("🚀 LabDetector 项目终极一键推送工具")
    print("=" * 60)

    # 1. 安全检查
    check_and_fix_gitignore()

    # 2. 获取当前状态
    success, status_out = run_cmd("git status -s", show_output=False)
    if not status_out:
        print("✅ 当前工作区很干净，没有需要提交的代码。")
        return

    print("📋 待提交的更改 (已自动屏蔽模型与日志等垃圾文件)：")
    print(status_out)

    # 3. 询问提交信息
    commit_msg = input("\n💬 请输入本次更新的说明 (直接回车默认: 'Auto update'): ").strip()
    if not commit_msg:
        commit_msg = f"Auto update: {time.strftime('%Y-%m-%d %H:%M')}"

    # 4. 执行 Git 工作流
    print("\n⏳ 1/4 正在添加文件到暂存区...")
    run_cmd("git add .")

    print("⏳ 2/4 正在提交更改...")
    run_cmd(f'git commit -m "{commit_msg}"', show_output=False)

    print("⏳ 3/4 正在拉取远程最新代码 (防止冲突)...")
    # 你的错误 `error: cannot pull with rebase` 是因为有未提交的改动，现在我们 commit 过了，用标准 pull 即可
    success, err = run_cmd("git pull origin master --no-edit", ignore_error=True)
    if not success and "fatal" in err:
        print(f"⚠️ 拉取出现问题: {err}")

    print("⏳ 4/4 正在推送到 GitHub 云端...")
    success, err = run_cmd("git push origin master")

    if success:
        print("\n🎉 推送成功！代码已安全备份到 GitHub！")
        # 推送成功后自动清理可能残留的代理，防止影响其他库
        run_cmd("git config --global --unset http.proxy", show_output=False, ignore_error=True)
        run_cmd("git config --global --unset https.proxy", show_output=False, ignore_error=True)
    else:
        if "Connection was reset" in err or "Timed out" in err or "443" in err:
            if handle_network_failure():
                # 设置代理后重试
                retry_success, retry_err = run_cmd("git push origin master")
                if retry_success:
                    print("\n🎉 代理穿透成功！代码已推送至 GitHub！")
                else:
                    print(f"\n❌ 代理重试依然失败，请检查您的梯子是否开启。\n{retry_err}")
        else:
            print(f"\n❌ 推送遇到未知错误：\n{err}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消推送。")