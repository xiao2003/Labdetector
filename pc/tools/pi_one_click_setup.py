#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PC 侧一键配置树莓派入口。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
PC_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_DIR = REPO_ROOT / "installer"
DEFAULT_CONFIG_PATH = PC_ROOT / "pi_one_click_setup.json"
LOG_DIR = PC_ROOT / "log"
PUTTY_DIR = Path(r"C:\Program Files\PuTTY")
PLINK = PUTTY_DIR / "plink.exe"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PC 一键配置树莓派并触发后台自治安装")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="一键配置文件路径")
    return parser.parse_args()


class PiOneClickSetup:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.config = self._load_config(config_path)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = LOG_DIR / f"pi_one_click_setup_{timestamp}.log"
        self.report_path = LOG_DIR / f"pi_one_click_setup_{timestamp}.json"
        self.report: Dict[str, Any] = {
            "success": False,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "config_path": str(config_path),
            "steps": [],
            "errors": [],
            "discovered_host": "",
            "pc_wifi_ssid": "",
            "pi_wifi_ip": "",
            "status_command": "",
            "log_command": "",
            "start_command": "",
        }
        self.remote_project_dir = f"/home/{self.config['ssh']['user']}/NeuroLab/pi"
        self.resolved_hostkey = ""
        self.resolved_wifi_ssid = ""
        self.resolved_wifi_password = ""

    def _log(self, text: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}"
        print(line)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _add_step(self, name: str, **payload: Any) -> None:
        row = {"name": name, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
        row.update(payload)
        self.report["steps"].append(row)

    @staticmethod
    def _load_config(path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise RuntimeError(f"一键配置文件不存在：{path}")
        config = json.loads(path.read_text(encoding="utf-8"))
        PiOneClickSetup._validate_config(config)
        return config

    @staticmethod
    def _validate_config(config: Dict[str, Any]) -> None:
        ssh_cfg = dict(config.get("ssh") or {})

        required_fields = {
            "ssh.user": str(ssh_cfg.get("user") or "").strip(),
            "ssh.password": str(ssh_cfg.get("password") or "").strip(),
        }
        placeholder_tokens = {
            "",
            "请填写",
            "请改成你的树莓派用户名",
            "请改成你的树莓派密码",
            "your_pi_user",
            "your_pi_password",
        }
        invalid_fields = [key for key, value in required_fields.items() if value in placeholder_tokens]
        if invalid_fields:
            raise RuntimeError(
                "一键配置文件缺少真实现场参数，请先在 pc/pi_one_click_setup.json 中填写："
                + "、".join(invalid_fields)
            )

    @staticmethod
    def _run(command: List[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            cwd=str(REPO_ROOT),
        )

    def _plink_base(self, host: str) -> List[str]:
        ssh_cfg = self.config["ssh"]
        command = [
            str(PLINK),
            "-batch",
            "-ssh",
            "-pw",
            ssh_cfg["password"],
            f"{ssh_cfg['user']}@{host}",
        ]
        if self.resolved_hostkey:
            command[5:5] = ["-hostkey", self.resolved_hostkey]
        return command

    def _remote_run(self, host: str, command: str, timeout: int = 600) -> str:
        result = self._run([*self._plink_base(host), command], timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(result.stdout.strip() or f"远程命令失败: {command}")
        return result.stdout

    def _current_wifi_ssid(self) -> str:
        result = self._run(["netsh", "wlan", "show", "interfaces"], timeout=60)
        text = result.stdout
        for line in text.splitlines():
            if re.match(r"^\s*SSID\s*:\s*", line, flags=re.IGNORECASE) and "BSSID" not in line.upper():
                return line.split(":", 1)[1].strip()
        return ""

    def _current_wifi_password(self, ssid: str) -> str:
        if not ssid:
            return ""
        result = self._run(["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"], timeout=60)
        for line in result.stdout.splitlines():
            if "Key Content" in line:
                return line.split(":", 1)[1].strip()
        return ""

    def _resolve_wifi_credentials(self) -> tuple[str, str]:
        wifi_cfg = dict(self.config.get("wifi") or {})
        configured_ssid = str(wifi_cfg.get("ssid") or "").strip()
        configured_password = str(wifi_cfg.get("password") or "").strip()
        placeholder_tokens = {"", "your_wifi_ssid", "your_wifi_password", "请改成你的wifi名称", "请改成你的wifi密码"}

        current_ssid = self._current_wifi_ssid()
        current_password = self._current_wifi_password(current_ssid)

        ssid = current_ssid if configured_ssid in placeholder_tokens else configured_ssid
        password = current_password if configured_password in placeholder_tokens else configured_password
        if not ssid or not password:
            raise RuntimeError("无法自动识别当前 PC 的 Wi‑Fi 名称或密码，请在 pc/pi_one_click_setup.json 中补充 wifi.ssid 和 wifi.password。")
        self.resolved_wifi_ssid = ssid
        self.resolved_wifi_password = password
        return ssid, password

    def _probe_with_cached_hostkey(self, host: str) -> bool:
        try:
            result = self._run(
                [
                    str(PLINK),
                    "-batch",
                    "-ssh",
                    "-pw",
                    self.config["ssh"]["password"],
                    f"{self.config['ssh']['user']}@{host}",
                    "echo ok",
                ],
                timeout=20,
            )
        except Exception:
            return False
        return result.returncode == 0 and "ok" in result.stdout

    def _trust_hostkey_once(self, host: str) -> bool:
        try:
            result = subprocess.run(
                [
                    str(PLINK),
                    "-ssh",
                    "-pw",
                    self.config["ssh"]["password"],
                    f"{self.config['ssh']['user']}@{host}",
                    "echo ok",
                ],
                input="y\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=30,
            )
        except Exception:
            return False
        return result.returncode == 0 and "ok" in result.stdout

    def _resolve_hostkey(self, host: str) -> None:
        configured_hostkey = str((self.config.get("ssh") or {}).get("hostkey") or "").strip()
        placeholder_tokens = {"", "your_pi_hostkey", "请改成你的树莓派 host key"}
        if configured_hostkey not in placeholder_tokens:
            self.resolved_hostkey = configured_hostkey
            return
        if self._probe_with_cached_hostkey(host):
            self.resolved_hostkey = ""
            self._add_step("ssh_hostkey_reused_from_cache", host=host)
            return
        if self._trust_hostkey_once(host):
            self.resolved_hostkey = ""
            self._add_step("ssh_hostkey_trusted_first_seen", host=host)
            return
        raise RuntimeError("无法自动建立树莓派 SSH host key 信任，请手动执行一次 SSH 登录或在配置文件中填写 ssh.hostkey。")

    def _ssh_probe(self, host: str) -> bool:
        if not host:
            return False
        try:
            result = self._run([*self._plink_base(host), "echo ok"], timeout=20)
        except Exception:
            return False
        return result.returncode == 0 and "ok" in result.stdout

    def _candidate_hosts(self) -> List[str]:
        hosts: List[str] = []
        preferred = str(self.config.get("preferred_host") or "").strip()
        if preferred:
            hosts.append(preferred)
        hosts.extend([str(item).strip() for item in self.config.get("candidate_hosts", []) if str(item).strip()])
        if "raspberrypi.local" not in hosts:
            hosts.append("raspberrypi.local")

        arp_result = self._run(["arp", "-a"], timeout=30)
        for line in arp_result.stdout.splitlines():
            match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
            if not match:
                continue
            ip = match.group(1)
            if ip not in hosts:
                hosts.append(ip)
        return hosts

    def discover_pi(self) -> str:
        for host in self._candidate_hosts():
            self._log(f"[INFO] 尝试探测树莓派 SSH 主机: {host}")
            try:
                self._resolve_hostkey(host)
            except Exception as exc:
                self._log(f"[WARN] SSH 指纹准备失败，跳过候选主机 {host}: {exc}")
                continue
            if self._ssh_probe(host):
                self.report["discovered_host"] = host
                self._add_step("pi_discovered", host=host)
                return host
        raise RuntimeError("未发现可 SSH 登录的树莓派，请先确保 Pi 已开机且 SSH 可用。")

    def ensure_ssh(self, host: str) -> None:
        password = self.config["ssh"]["password"]
        command = (
            f"echo {json.dumps(password)} | sudo -S systemctl enable ssh && "
            f"echo {json.dumps(password)} | sudo -S systemctl restart ssh"
        )
        self._remote_run(host, command, timeout=300)
        self._add_step("ssh_enabled", host=host)

    def connect_wifi(self, host: str) -> str:
        ssid, password = self._resolve_wifi_credentials()

        self.report["pc_wifi_ssid"] = self._current_wifi_ssid()
        self._add_step("pc_wifi_detected", ssid=self.report["pc_wifi_ssid"])

        remote_command = (
            f"echo {json.dumps(self.config['ssh']['password'])} | sudo -S nmcli radio wifi on && "
            f"echo {json.dumps(self.config['ssh']['password'])} | sudo -S nmcli dev wifi connect {json.dumps(ssid)} password {json.dumps(password)} || true && "
            "hostname -I"
        )
        output = self._remote_run(host, remote_command, timeout=300)
        ipv4_match = re.findall(r"\b\d+\.\d+\.\d+\.\d+\b", output)
        wifi_ip = ipv4_match[-1] if ipv4_match else host
        self.report["pi_wifi_ip"] = wifi_ip
        self._add_step("pi_wifi_connected", target_ssid=ssid, wifi_ip=wifi_ip)
        return wifi_ip

    def deploy_and_trigger(self, host: str) -> Dict[str, Any]:
        deploy_script = INSTALLER_DIR / "deploy_pi_code_and_trigger.py"
        ssh_cfg = self.config["ssh"]
        result = self._run(
            [
                sys.executable,
                str(deploy_script),
                "--host",
                host,
                "--user",
                ssh_cfg["user"],
                "--password",
                ssh_cfg["password"],
                "--hostkey",
                ssh_cfg["hostkey"],
            ],
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stdout.strip() or "投递代码并触发安装失败")
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.remote_project_dir = str(payload.get("remote_project_dir") or self.remote_project_dir)
        self.report["status_command"] = payload.get("status_command", "")
        self.report["log_command"] = payload.get("log_command", "")
        self.report["start_command"] = payload.get("start_command", "")
        self._add_step("deploy_triggered", **payload)
        return payload

    def poll_install(self, host: str) -> Dict[str, Any]:
        timeout_seconds = int(self.config.get("install_timeout_seconds") or 14400)
        interval_seconds = int(self.config.get("poll_interval_seconds") or 60)
        started_at = time.time()
        while time.time() - started_at < timeout_seconds:
            output = self._remote_run(
                host,
                f"cd {self.remote_project_dir} && python3 pi_cli.py install-status --json",
                timeout=120,
            )
            status = json.loads(output.strip().splitlines()[-1])
            self._add_step("install_status_polled", status=status.get("status"), stage=status.get("stage"), running=status.get("running"))
            self._log(f"[INFO] 安装状态: status={status.get('status')} stage={status.get('stage')} running={status.get('running')}")
            if status.get("status") == "success":
                return status
            if status.get("status") == "failed":
                raise RuntimeError(f"Pi 后台安装失败: {status.get('error')}")
            time.sleep(interval_seconds)
        raise RuntimeError("等待 Pi 运行时安装超时。")

    def start_pi_runtime(self, host: str) -> None:
        command = (
            f"cd {self.remote_project_dir} && "
            "nohup bash start_pi_node.sh > runtime_state/node_runtime.log 2>&1 < /dev/null &"
        )
        self._remote_run(host, command, timeout=120)
        self._add_step("pi_runtime_started", host=host)

    def run(self) -> int:
        try:
            host = self.discover_pi()
            self.ensure_ssh(host)
            host = self.connect_wifi(host)
            self.deploy_and_trigger(host)
            install_status = self.poll_install(host)
            self._add_step("install_completed", **install_status)
            self.start_pi_runtime(host)
            self.report["success"] = True
            return 0
        except Exception as exc:
            self.report["errors"].append(str(exc))
            self._log(f"[ERROR] {exc}")
            return 1
        finally:
            self.report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self.report_path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    runner = PiOneClickSetup(Path(args.config).resolve())
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
