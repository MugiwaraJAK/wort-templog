# -*- coding: utf-8 -*-
import collections
import json
import config

_FIELD_DEFAULTS = {
    'fridge_setpoint': 16,
    'fridge_difference': 0.2,
    'overshoot_delay': 720, # 12 minutes
    'overshoot_factor': 1, # ºC
    }

class Params(dict):
    class Error(Exception):
        pass

    def __init__(self):
        self.update(_FIELD_DEFAULTS)

    def __getattr__(self, k):
        return self[k]

    def __setattr__(self, k, v):
        # fail if we set a bad value
        self[k]
        self[k] = v

    def load(self, f = None):
        if not f:
            f = file(config.PARAMS_FILE, 'r')
        u = json.load(f)
        for k in u:
            if k not in self:
                raise self.Error("Unknown parameter %s=%s in file '%s'" % (str(k), str(u[k]), getattr(f, 'name', '???')))
        self.update(u)

    def save(self, f = None):
        if not f:
            f = file(config.PARAMS_FILE, 'w')
        json.dump(self, f, sort_keys=True, indent=4)
        f.flush()
