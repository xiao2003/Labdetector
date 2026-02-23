# piside/config.py
import configparser
import os
import json

class PiConfig:
    _config = None
    _config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

    @classmethod
    def init(cls):
        if cls._config is not None: return
        cls._config = configparser.ConfigParser()
        if not os.path.exists(cls._config_path):
            cls._create_default()
        cls._config.read(cls._config_path, encoding='utf-8')

    @classmethod
    def _create_default(cls):
        config = configparser.ConfigParser()
        config['voice'] = {
            'wake_word': '小爱同学',
            'online_recognition': 'True',
            'model_path': 'voice/model'
        }
        config['network'] = {'pc_ip': '', 'ws_port': '8001'}
        with open(cls._config_path, 'w', encoding='utf-8') as f:
            config.write(f)

    @classmethod
    def get(cls, key_path, default=None):
        cls.init()
        section, key = key_path.split('.')
        if section not in cls._config or key not in cls._config[section]:
            return default
        val = cls._config[section][key]
        if val.lower() == 'true': return True
        if val.lower() == 'false': return False
        return val

    @classmethod
    def set(cls, key_path, value):
        cls.init()
        section, key = key_path.split('.')
        if section not in cls._config: cls._config[section] = {}
        cls._config[section][key] = str(value)
        with open(cls._config_path, 'w', encoding='utf-8') as f:
            cls._config.write(f)

def get_pi_config(key, default=None): return PiConfig.get(key, default)
def set_pi_config(key, value): PiConfig.set(key, value)