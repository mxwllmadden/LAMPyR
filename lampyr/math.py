# -*- coding: utf-8 -*-
"""
Created on Mon Jun 15 14:58:17 2026

@author: mm4114
"""
import random

def rand_int_uniform_hazard(hazard, min_val = 1, max_val = None):
    i = min_val
    while True:
        if random.random() < hazard:
            return i
        if i >= max_val:
            return i
        i += 1

def near_uniform_hazard(min_val=1, max_val=10):
    N = max_val - min_val + 1

    if N == 1:
        return 1.0

    return 1 - N**(-1/(N-1))

def rand_int_uniform_hazard_auto(min_val, max_val):
    h = near_uniform_hazard(min_val, max_val)
    return rand_int_uniform_hazard(h, min_val, max_val)
