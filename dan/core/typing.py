from typing import *

def is_optional(field):
    return get_origin(field) is Union and \
           type(None) in get_args(field)
