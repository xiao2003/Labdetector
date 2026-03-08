import configparser
import os
from typing import Any


class PiConfig:
    _config = None
    _config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

    @classmethod
    def init(cls) -> None:
        if cls._config is not None:
            return
        cls._config = configparser.ConfigParser()
        if not os.path.exists(cls._config_path):
            cls._create_default()
        cls._config.read(cls._config_path, encoding="utf-8-sig")
        cls._ensure_defaults()

    @classmethod
    def _create_default(cls) -> None:
        config = configparser.ConfigParser()
        config["voice"] = {
            "wake_word": "小爱同学",
            "online_recognition": "True",
            "model_path": "voice/model",
        }
        config["network"] = {"pc_ip": "", "ws_port": "8001"}
        config["detector"] = {
            "weights_path": "yolov8n.pt",
            "conf": "0.4",
            "imgsz": "640",
        }
        config["self_check"] = {
            "auto_install_dependencies": "True",
        }
        with open(cls._config_path, "w", encoding="utf-8-sig") as handle:
            config.write(handle)

    @classmethod
    def _ensure_defaults(cls) -> None:
        defaults = {
            "voice": {
                "wake_word": "小爱同学",
                "online_recognition": "True",
                "model_path": "voice/model",
            },
            "network": {"pc_ip": "", "ws_port": "8001"},
            "detector": {
                "weights_path": "yolov8n.pt",
                "conf": "0.4",
                "imgsz": "640",
            },
            "self_check": {
                "auto_install_dependencies": "True",
            },
        }
        changed = False
        assert cls._config is not None
        for section, options in defaults.items():
            if section not in cls._config:
                cls._config[section] = {}
                changed = True
            for key, value in options.items():
                if key not in cls._config[section]:
                    cls._config[section][key] = str(value)
                    changed = True
        if changed:
            with open(cls._config_path, "w", encoding="utf-8-sig") as handle:
                cls._config.write(handle)

    @classmethod
    def get(cls, key_path: str, default: Any = None):
        cls.init()
        section, key = key_path.split(".", 1)
        if section not in cls._config or key not in cls._config[section]:
            return default
        value = cls._config[section][key]
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    @classmethod
    def set(cls, key_path: str, value: Any) -> None:
        cls.init()
        section, key = key_path.split(".", 1)
        if section not in cls._config:
            cls._config[section] = {}
        cls._config[section][key] = str(value)
        with open(cls._config_path, "w", encoding="utf-8-sig") as handle:
            cls._config.write(handle)


def get_pi_config(key, default=None):
    return PiConfig.get(key, default)


def set_pi_config(key, value):
    PiConfig.set(key, value)
