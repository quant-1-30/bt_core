import os
import glob
from setup import get_ext_modules

def build(setup_kwargs): # trigger by poetry

    setup_kwargs.update({
        "ext_modules":get_ext_modules()
    })
