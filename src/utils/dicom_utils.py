import numpy as np
import pydicom

def normalize_pixel_array(pixel_array):
    if pixel_array.dtype != np.uint8:
        return ((pixel_array - pixel_array.min()) /
                (pixel_array.max() - pixel_array.min()) * 255).astype(np.uint8)
    return pixel_array

def get_tag_value_str(elem):
    if isinstance(elem.value, bytes):
        return "<binary data>"
    elif isinstance(elem.value, pydicom.sequence.Sequence):
        return f"<sequence of {len(elem.value)} items>"
    return str(elem.value)
