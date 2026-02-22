import subprocess
import sys


def run_command(command: str) -> subprocess.CompletedProcess:
    """
    执行系统命令的安全包装器。
    加入 encoding='utf-8' 和 errors='replace' 彻底解决 Windows 下的 GBK 乱码崩溃问题。
    """
    return subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'  # 遇到无法解码的字符直接替换为 '?'，绝不引发程序崩溃
    )


def main():
    print("========================================")
    print("   🚀 一键推送项目到 GitHub   ")
    print("========================================")

    # 1. 获取当前分支
    branch_process = run_command("git branch --show-current")
    current_branch = branch_process.stdout.strip()

    if not current_branch:
        print("❌ 错误：无法获取当前分支，请检查当前目录是否为 Git 仓库。")
        return

    print(f"📍 当前分支：{current_branch}")

    # 2. 检查是否有需要提交的更改
    status_process = run_command("git status --porcelain")
    changes = status_process.stdout.strip()

    if not changes:
        print("✨ 当前工作区很干净，没有需要提交的更改。")
        return

    print("📋 待提交的更改：")
    for line in changes.split('\n'):
        print(f"  {line}")

    # 3. 获取提交信息
    commit_msg = input("\n💬 请输入提交信息：").strip()
    if not commit_msg:
        print("⚠️ 提交信息不能为空，请重新运行脚本！")
        return

    # 4. 执行 Git 流程
    print("⏳ 正在添加文件...")
    add_process = run_command("git add .")
    if add_process.returncode != 0:
        print(f"❌ 添加文件失败：\n{add_process.stderr}")
        return

    print("⏳ 正在提交...")
    commit_process = run_command(f'git commit -m "{commit_msg}"')
    if commit_process.returncode != 0 and "nothing to commit" not in commit_process.stdout:
        print(f"❌ 提交失败：\n{commit_process.stderr}")
        return

    print("⏳ 正在拉取远程代码...")
    # 加上 --rebase 可以避免产生多余的合并节点
    pull_process = run_command(f"git pull origin {current_branch} --rebase")
    if pull_process.returncode != 0:
        print(f"⚠️ 拉取远程代码可能存在冲突或警告，但不影响继续推送：\n{pull_process.stderr}")

    print("⏳ 正在推送...")
    push_process = run_command(f"git push origin {current_branch}")

    if push_process.returncode == 0:
        print("========================================")
        print("   ✅ 推送成功！")
        print("========================================")
    else:
        print("❌ 推送失败，请检查以下错误信息：")
        print(push_process.stderr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 已手动取消推送操作。")
        sys.exit(0)