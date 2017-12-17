# The MIT License (MIT)
#
# Copyright (c) 2015 Sean Hagar
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Modifications by Steve Johnson:
# * Remove all libtcod-specific code
# * Docstrings
# * Python 3
"""
Load the `REXPaint <http://www.gridsagegames.com/rexpaint/>`_ file format. If
you're using this with the rest of clubsandwich and not just by itself, you
probably want to check out :py:mod:`clubsandwich.blt.rexpaint_image` instead!
It's much nicer.

In-memory XP format is as follows:

Returned structure is a dictionary with the keys ``version``, ``layers``,
``width``, ``height``, and ``layer_data``.

* ``version`` is stored in case it's useful for someone, but as mentioned in the
  format description it probably won't be unless format changes happen.
* ``layers`` is a full 32 bit int, though right now REXPaint only exports or
  manages up to 4 layers.
* ``width`` and ``height`` are extracted from the layer with largest width and
  height - this value will hold true for all layers for now as per the format
  description.
* ``layer_data`` is a list of individual layers, which are stored in the
  following format:

  * Each layer is a dictionary with keys ``width``, ``height`` (see above),
    and ``cells``. 
  * ``cells`` is a row major 2d array of, again, dictionaries with the values
    ``keycode`` (ascii keycode), ``fore_r/g/b``, and ``back_r/g/b``
    (technically ints but in value 0-255)
"""

import base64
import gzip


##################################
# Used primarily internally to parse the data, feel free to reference them externally if it's useful.
# Changing these programattically will, of course, screw up the parsing (unless the format changes and you're using an old copy of this file)
##################################

version_bytes = 4
layer_count_bytes = 4

layer_width_bytes = 4
layer_height_bytes = 4
layer_keycode_bytes = 4
layer_fore_rgb_bytes = 3
layer_back_rgb_bytes = 3
layer_cell_bytes = layer_keycode_bytes + \
    layer_fore_rgb_bytes + layer_back_rgb_bytes


##################################
# REXPaint color key for transparent background colors. Not directly used here, but you should reference this when calling libtcod's console_set_key_color on offscreen consoles.
##################################

transparent_cell_back_r = 255
transparent_cell_back_g = 0
transparent_cell_back_b = 255


def load_xp_file(path, reverse_endian=True):
    """
    Load a REXPaint image from the given ``.xp`` path.

    :param str path: Path to a ``.xp`` file
    :param bool reverse_endian: Controls whether the slices containing data for
                                things like layer width, height, number of layers,
                                etc. is reversed. So far as I can tell Python is
                                doing int conversions in big-endian, while the
                                ``.xp`` format stores them in little-endian.
                                I may just not be aware of it being unneeded, but
                                have it there in case.
    """
    with gzip.open(path) as f:
        return load_xp_string(f.read(), reverse_endian=reverse_endian)


def _bytes_to_int(bts):
    return int(base64.b16encode(bts), 16)


def load_xp_string(file_string, reverse_endian=True):
    """
    :param str file_string: String contents of a ``.xp`` file generated by
                            REXPaint
    :param bool reverse_endian: Controls whether the slices containing data for
                                things like layer width, height, number of layers,
                                etc. is reversed. So far as I can tell Python is
                                doing int conversions in big-endian, while the
                                ``.xp`` format stores them in little-endian.
                                I may just not be aware of it being unneeded, but
                                have it there in case.
    """
    offset = 0

    version = file_string[offset: offset + version_bytes]
    offset += version_bytes
    layer_count = file_string[offset: offset + layer_count_bytes]
    offset += layer_count_bytes

    if reverse_endian:
        version = version[::-1]
        layer_count = layer_count[::-1]

    # hex-encodes the numbers then converts them to an int
    version = _bytes_to_int(version)
    layer_count = _bytes_to_int(layer_count)

    layers = []

    current_largest_width = 0
    current_largest_height = 0

    for layer in range(layer_count):
        # slight lookahead to figure out how much data to feed load_layer

        this_layer_width = file_string[offset:offset + layer_width_bytes]
        this_layer_height = file_string[offset +
                                        layer_width_bytes:offset + layer_width_bytes + layer_height_bytes]

        if reverse_endian:
            this_layer_width = this_layer_width[::-1]
            this_layer_height = this_layer_height[::-1]

        this_layer_width = _bytes_to_int(this_layer_width)
        this_layer_height = _bytes_to_int(this_layer_height)

        current_largest_width = max(current_largest_width, this_layer_width)
        current_largest_height = max(current_largest_height, this_layer_height)

        layer_data_size = layer_width_bytes + layer_height_bytes + \
            (layer_cell_bytes * this_layer_width * this_layer_height)

        layer_data_raw = file_string[offset:offset + layer_data_size]
        layer_data = _parse_layer(
            file_string[offset:offset + layer_data_size], reverse_endian)
        layers.append(layer_data)

        offset += layer_data_size

    return {
        'version': version,
        'layer_count': layer_count,
        'width': current_largest_width,
        'height': current_largest_height,
        'layer_data': layers
    }


def _parse_layer(layer_string, reverse_endian=True):
    """
    Takes a single layer's data and returns the format listed in the module docstring
    for a single layer.
    """
    offset = 0

    width = layer_string[offset:offset + layer_width_bytes]
    offset += layer_width_bytes
    height = layer_string[offset:offset + layer_height_bytes]
    offset += layer_height_bytes

    if reverse_endian:
        width = width[::-1]
        height = height[::-1]

    width = _bytes_to_int(width)
    height = _bytes_to_int(height)

    cells = []
    for x in range(width):
        row = []

        for y in range(height):
            cell_data_raw = layer_string[offset:offset + layer_cell_bytes]
            cell_data = _parse_individual_cell(cell_data_raw, reverse_endian)
            row.append(cell_data)
            offset += layer_cell_bytes

        cells.append(row)

    return {
        'width': width,
        'height': height,
        'cells': cells
    }


def _parse_individual_cell(cell_string, reverse_endian=True):
    """
    Pulls out the keycode and the foreground/background RGB values from a single
    cell's data, returning them in the format listed at the top of this file for
    a single cell.
    """
    offset = 0

    keycode = cell_string[offset:offset + layer_keycode_bytes]
    if reverse_endian:
        keycode = keycode[::-1]
    keycode = _bytes_to_int(keycode)
    offset += layer_keycode_bytes

    fore_r = _bytes_to_int(cell_string[offset:offset + 1])
    offset += 1
    fore_g = _bytes_to_int(cell_string[offset:offset + 1])
    offset += 1
    fore_b = _bytes_to_int(cell_string[offset:offset + 1])
    offset += 1

    back_r = _bytes_to_int(cell_string[offset:offset + 1])
    offset += 1
    back_g = _bytes_to_int(cell_string[offset:offset + 1])
    offset += 1
    back_b = _bytes_to_int(cell_string[offset:offset + 1])
    offset += 1

    return {
        'keycode': keycode,
        'fore_r': fore_r,
        'fore_g': fore_g,
        'fore_b': fore_b,
        'back_r': back_r,
        'back_g': back_g,
        'back_b': back_b,
    }
