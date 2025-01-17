import numpy as np
import pydicom


def normalize_pixel_array(pixel_array):
    if pixel_array.dtype != np.uint8:
        return ((pixel_array - pixel_array.min()) /
                (pixel_array.max() - pixel_array.min()) * 255).astype(np.uint8)
    return pixel_array


def get_tag_value_str(elem):
    if isinstance(elem.value, bytes):
        return "<binary data>", False
    elif isinstance(elem.value, pydicom.sequence.Sequence):
        sequence_items = get_sequence_items(elem.value)
        return f"<sequence of {len(elem.value)} items>", sequence_items
    return str(elem.value), False


def get_sequence_items(sequence):
    items = []
    for i, item in enumerate(sequence):
        sequence_item = {
            'index': i,
            'elements': []
        }
        for elem in item:
            if elem.tag.group != 0x7FE0:
                sequence_item['elements'].append({
                    'tag': (elem.tag.group, elem.tag.element),
                    'name': elem.name,
                    'vr': getattr(elem, "VR", ""),
                    'value': get_tag_value_str(elem)
                })
        items.append(sequence_item)
    return items
