# -*- coding: utf-8 -*-
"""
Created on Mon Aug 25 19:47:06 2025

@author: mm4114
"""
from lampyr.version import __version__

import os, json, time
from copy import deepcopy

class ConfigFile:
    def __init__(self, default_config : dict, fp : str):
        loaded_config = {}
        if os.path.exists(fp):
            try:
                with open(fp, 'r') as f:
                    loaded_config = json.load(f)
            except Exception:
                pass
        self._config = self._merge_configs(deepcopy(default_config), loaded_config)
        self._default = deepcopy(default_config)
        self._syncfp = fp

    def _merge_configs(self, default, loaded):
        for key, value in default.items():
            if key in loaded and isinstance(value, dict) and isinstance(loaded[key], dict):
                loaded[key] = self._merge_configs(value, loaded[key])
            elif key not in loaded:
                loaded[key] = value
        return loaded

    def get(self, key_path):
        keys = key_path.split('.')
        current = self._config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                raise KeyError(f"Key not found: {key_path}")
        return deepcopy(current)

    def set(self, key_path, value):
        keys = key_path.split('.')
        current = self._config
        for key in keys[:-1]:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                raise KeyError(f"Key path not found: {key_path}")
        current[keys[-1]] = value
        self.save()
    
    def save(self):
        with open(self._syncfp, 'w') as file:
            json.dump(self.to_dict(), file, indent = 2)
    
    def to_dict(self):
        return deepcopy(self._config)


class Config(ConfigFile):
    _APP_DATA_DIR = os.path.join(os.getenv('LOCALAPPDATA'), 'lampyr')
    _CONFIG_FILE_PATH = os.path.join(_APP_DATA_DIR, 'config.json')

    DEFAULT_CONFIG = {
        'lampyr': {
            'configured': False,
            'mice_directory': 'N:/SHARED/Maxwell_Lampyr_MouseData',
            'enable_saveload_failsafe': True,
            'enable_local_mouse_backups' : True
        },
        'rig': {
            'name': None,
            'calibrated': 0,
            'configured': False,
            'sipper_calib': 10000
        },
        'notifications': {
            'last_user' : 'mixwell'
        }
    }

    def __init__(self):
        os.makedirs(self._APP_DATA_DIR, exist_ok=True)
        super().__init__(self.DEFAULT_CONFIG, self._CONFIG_FILE_PATH)
        self.set('lampyr.version', __version__)
    
    def load_extended_config(self, key, default = {}):
        fp = os.path.join(self._APP_DATA_DIR, f'{key}.json')
        return ConfigFile(default, fp)

    def load_shared_extended_config(self, key, default = {}):
        shared_dir = self.get('lampyr.mice_directory')
        fp = os.path.join(shared_dir, f'{key}.json')
        return ConfigFile(default, fp)