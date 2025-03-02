import torch
import torch.nn.functional as F

import re
import functools

from comfy.samplers import SCHEDULER_NAMES

from .res4lyf import RESplain




# EXTRA_OPTIONS OPS

class ExtraOptions():
    def __init__(self, extra_options):
        self.extra_options = extra_options
        
    def __call__(self, option, default=None, ret_type=None, match_all_flags=False):
        if isinstance(option, (tuple, list)):
            if match_all_flags:
                return all(self(single_option, default, ret_type) for single_option in option)
            else:
                return any(self(single_option, default, ret_type) for single_option in option)

        if default is None: # get flag
            pattern = rf"^(?:{re.escape(option)}\s*$|{re.escape(option)}=)"
            return bool(re.search(pattern, self.extra_options, flags=re.MULTILINE))
        elif ret_type is None:
            ret_type = type(default)
        
            if ret_type.__module__ != "builtins":
                mod = __import__(default.__module__)
                ret_type = lambda v: getattr(mod, v, None)
        
        if ret_type == list:
            pattern = rf"^{re.escape(option)}\s*=\s*([a-zA-Z0-9_.,+-]+)\s*$"
            match   = re.search(pattern, self.extra_options, flags=re.MULTILINE)
            
            if match:
                value = match.group(1)
            else:
                value = default
                
            if type(value) == str:
                value = value.split(',')
            
                if type(default[0]) == type:
                    ret_type = default[0]
                else:
                    ret_type = type(default[0])
                
                value = [ret_type(value[_]) for _ in range(len(value))]
        
        else:
            pattern = rf"^{re.escape(option)}\s*=\s*([a-zA-Z0-9_.+-]+)\s*$"
            match = re.search(pattern, self.extra_options, flags=re.MULTILINE)
            if match:
                value = ret_type(match.group(1))
            else:
                value = default
        
        return value




def extra_options_flag(flag, extra_options):
    pattern = rf"^(?:{re.escape(flag)}\s*$|{re.escape(flag)}=)"
    return bool(re.search(pattern, extra_options, flags=re.MULTILINE))

def get_extra_options_kv(key, default, extra_options, ret_type=None):
    ret_type = type(default) if ret_type is None else ret_type

    pattern = rf"^{re.escape(key)}\s*=\s*([a-zA-Z0-9_.+-]+)\s*$"
    match = re.search(pattern, extra_options, flags=re.MULTILINE)
    
    if match:
        value = match.group(1)
    else:
        value = default
        
    return ret_type(value)

def get_extra_options_list(key, default, extra_options, ret_type=None):
    default = [default] if type(default) != list else default
    
    #ret_type = type(default)    if ret_type is None else ret_type
    ret_type = type(default[0]) if ret_type is None else ret_type

    pattern = rf"^{re.escape(key)}\s*=\s*([a-zA-Z0-9_.,+-]+)\s*$"
    match   = re.search(pattern, extra_options, flags=re.MULTILINE)
    
    if match:
        value = match.group(1)
    else:
        value = default
    
    if type(value) == str:
        value = value.split(',')
    
    value = [ret_type(value[_]) for _ in range(len(value))]
        
    return value



class OptionsManager:
    APPEND_OPTIONS = {"extra_options"}

    def __init__(self, options, **kwargs):
        self.options_list = []
        if options is not None:
            self.options_list.append(options)

        for key, value in kwargs.items():
            if key.startswith('options') and value is not None:
                self.options_list.append(value)

        self._merged_dict = None

    def add_option(self, option):
        """Add a single options dictionary"""
        if option is not None:
            self.options_list.append(option)
            self._merged_dict = None # invalidate cached merged options

    @property
    def merged(self):
        """Get merged options with proper priority handling"""
        if self._merged_dict is None:
            self._merged_dict = {}

            special_string_options = {
                key: [] for key in self.APPEND_OPTIONS
            }

            for options_dict in self.options_list:
                if options_dict is not None:
                    for key, value in options_dict.items():
                        if key in self.APPEND_OPTIONS and value:
                            special_string_options[key].append(value)
                        elif isinstance(value, dict):
                            # Deep merge dictionaries
                            if key not in self._merged_dict:
                                self._merged_dict[key] = {}

                            if isinstance(self._merged_dict[key], dict):
                                self._deep_update(self._merged_dict[key], value)
                            else:
                                self._merged_dict[key] = value.copy()
                        else:
                            self._merged_dict[key] = value

            # append special case string options (e.g. extra_options)
            for key, value in special_string_options.items():
                if value:
                    self._merged_dict[key] = "\n".join(value)

        return self._merged_dict

    def get(self, key, default=None):
        return self.merged.get(key, default)

    def _deep_update(self, target_dict, source_dict):

        for key, value in source_dict.items():
            if isinstance(value, dict) and key in target_dict and isinstance(target_dict[key], dict):
                # recursive dict update
                self._deep_update(target_dict[key], value)
            else:
                target_dict[key] = value

    def __getitem__(self, key):
        """Allow dictionary-like access to options"""
        return self.merged[key]

    def __contains__(self, key):
        """Allow 'in' operator for options"""
        return key in self.merged

    def as_dict(self):
        """Return the merged options as a dictionary"""
        return self.merged.copy()

    def __bool__(self):
        """Return True if there are any options"""
        return len(self.options_list) > 0 and any(opt is not None for opt in self.options_list)

    def debug_print_options(self):
        for i, options_dict in enumerate(self.options_list):
            RESplain(f"Options {i}:", debug=True)
            if options_dict is not None:
                for key, value in options_dict.items():
                    RESplain(f"  {key}: {value}", debug=True)
            else:
                RESplain("  None", "\n", debug=True)





# MISCELLANEOUS OPS

def has_nested_attr(obj, attr_path):
    attrs = attr_path.split('.')
    for attr in attrs:
        if not hasattr(obj, attr):
            return False
        obj = getattr(obj, attr)
    return True

def safe_get_nested(d, keys, default=None):
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d





# COMFY OPS

def is_video_model(model):
    is_video_model = False
    try :
        is_video_model = 'video' in model.inner_model.inner_model.model_config.unet_config['image_model'] or \
                         'cosmos' in model.inner_model.inner_model.model_config.unet_config['image_model'] or \
                         'wan2' in model.inner_model.inner_model.model_config.unet_config['image_model'] or \
                         'ltxv' in model.inner_model.inner_model.model_config.unet_config['image_model']    
    except:
        pass
    return is_video_model

def is_RF_model(model):
    from comfy import model_sampling
    modelsampling = model.inner_model.inner_model.model_sampling
    return isinstance(modelsampling, model_sampling.CONST)

def get_res4lyf_scheduler_list():
    scheduler_names = SCHEDULER_NAMES.copy()
    if "beta57" not in scheduler_names:
        scheduler_names.append("beta57")
    return scheduler_names

def move_to_same_device(*tensors):
    if not tensors:
        return tensors
    device = tensors[0].device
    return tuple(tensor.to(device) for tensor in tensors)

def conditioning_set_values(conditioning, values={}):
    c = []
    for t in conditioning:
        n = [t[0], t[1].copy()]
        for k in values:
            n[1][k] = values[k]
        c.append(n)
    return c





# MISC OPS

def initialize_or_scale(tensor, value, steps):
    if tensor is None:
        return torch.full((steps,), value)
    else:
        return value * tensor



class PrecisionTool:
    def __init__(self, cast_type='fp64'):
        self.cast_type = cast_type

    def cast_tensor(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if self.cast_type not in ['fp64', 'fp32', 'fp16']:
                return func(*args, **kwargs)

            target_device = None
            for arg in args:
                if torch.is_tensor(arg):
                    target_device = arg.device
                    break
            if target_device is None:
                for v in kwargs.values():
                    if torch.is_tensor(v):
                        target_device = v.device
                        break
            
        # recursively zs_recast tensors in nested dictionaries
            def cast_and_move_to_device(data):
                if torch.is_tensor(data):
                    if self.cast_type == 'fp64':
                        return data.to(torch.float64).to(target_device)
                    elif self.cast_type == 'fp32':
                        return data.to(torch.float32).to(target_device)
                    elif self.cast_type == 'fp16':
                        return data.to(torch.float16).to(target_device)
                elif isinstance(data, dict):
                    return {k: cast_and_move_to_device(v) for k, v in data.items()}
                return data

            new_args = [cast_and_move_to_device(arg) for arg in args]
            new_kwargs = {k: cast_and_move_to_device(v) for k, v in kwargs.items()}
            
            return func(*new_args, **new_kwargs)
        return wrapper

    def set_cast_type(self, new_value):
        if new_value in ['fp64', 'fp32', 'fp16']:
            self.cast_type = new_value
        else:
            self.cast_type = 'fp64'

precision_tool = PrecisionTool(cast_type='fp64')



