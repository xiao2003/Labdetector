#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import sys
from datetime import datetime


class Colors:
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    NC = '\033[0m'


def run_command(cmd, check=True):
    """执行命令"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=check
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr


def main():
    print(f"{Colors.GREEN}{'=' * 40}{Colors.NC}")
    print(f"{Colors.GREEN}   🚀 一键推送项目到 GitHub   {Colors.NC}")
    print(f"{Colors.GREEN}{'=' * 40}{Colors.NC}")

    # 检查是否在 git 仓库
    success, _, _ = run_command("git rev-parse --git-dir", check=False)
    if not success:
        print(f"{Colors.RED}❌ 错误：当前目录不是 Git 仓库{Colors.NC}")
        sys.exit(1)

    # 获取当前分支
    _, branch, _ = run_command("git branch --show-current")
    branch = branch.strip()
    print(f"{Colors.YELLOW}📍 当前分支：{branch}{Colors.NC}")

    # 检查更改
    _, status, _ = run_command("git status --porcelain")
    if not status.strip():
        print(f"{Colors.YELLOW}⚠️  没有需要提交的更改{Colors.NC}")
        sys.exit(0)

    # 显示更改
    print(f"{Colors.YELLOW}📋 待提交的更改：{Colors.NC}")
    print(status)

    # 获取提交信息
    commit_msg = input(f"{Colors.YELLOW}💬 请输入提交信息：{Colors.NC}").strip()
    if not commit_msg:
        commit_msg = f"update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        print(f"{Colors.YELLOW}⚠️  使用默认提交信息：{commit_msg}{Colors.NC}")

    # 添加文件
    print(f"{Colors.GREEN}⏳ 正在添加文件...{Colors.NC}")
    run_command("git add .")

    # 提交
    print(f"{Colors.GREEN}⏳ 正在提交...{Colors.NC}")
    success, _, stderr = run_command(f'git commit -m "{commit_msg}"', check=False)
    if not success:
        print(f"{Colors.RED}❌ 提交失败：{stderr}{Colors.NC}")
        sys.exit(1)

    # 拉取
    print(f"{Colors.GREEN}⏳ 正在拉取远程代码...{Colors.NC}")
    run_command(f"git pull origin {branch} --rebase", check=False)

    # 推送
    print(f"{Colors.GREEN}⏳ 正在推送...{Colors.NC}")
    success, _, stderr = run_command(f"git push origin {branch}", check=False)

    if success:
        print(f"{Colors.GREEN}{'=' * 40}{Colors.NC}")
        print(f"{Colors.GREEN}   ✅ 推送成功！{Colors.NC}")
        print(f"{Colors.GREEN}{'=' * 40}{Colors.NC}")
    else:
        print(f"{Colors.RED}{'=' * 40}{Colors.NC}")
        print(f"{Colors.RED}   ❌ 推送失败{Colors.NC}")
        print(f"{Colors.RED}{'=' * 40}{Colors.NC}")
        print(stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()