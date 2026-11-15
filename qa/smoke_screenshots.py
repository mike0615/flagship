#!/usr/bin/env python3
"""Offscreen GUI smoke test: open Flagship and About, save PNG screenshots.

Intended for xvfb-run. Talks only to the local X display; never to a pool.
"""
from __future__ import annotations

import ctypes
import os
import struct
import sys
import time
import zlib
from ctypes import POINTER, byref, c_char, c_char_p, c_int, c_long, c_uint, c_ulong, c_void_p
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flagship.app import Application  # noqa: E402
from flagship.help import AboutDialog  # noqa: E402
import tkinter as tk  # noqa: E402


class XImage(ctypes.Structure):
    _fields_ = [
        ('width', c_int), ('height', c_int),
        ('xoffset', c_int), ('format', c_int),
        ('data', ctypes.POINTER(c_char)),
        ('byte_order', c_int), ('bitmap_unit', c_int),
        ('bitmap_bit_order', c_int), ('bitmap_pad', c_int),
        ('depth', c_int), ('bytes_per_line', c_int),
        ('bits_per_pixel', c_int),
        ('red_mask', c_ulong), ('green_mask', c_ulong), ('blue_mask', c_ulong),
    ]


def _mask_shift(mask: int) -> tuple[int, int]:
    if not mask:
        return 0, 0
    shift = 0
    while mask and not (mask & 1):
        mask >>= 1
        shift += 1
    bits = 0
    while mask & 1:
        mask >>= 1
        bits += 1
    return shift, bits


def write_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    rows = b''.join(b'\x00' + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as handle:
        handle.write(b'\x89PNG\r\n\x1a\n')
        handle.write(chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)))
        handle.write(chunk(b'IDAT', zlib.compress(rows, 9)))
        handle.write(chunk(b'IEND', b''))


def grab_window(window_id: int, path: Path) -> None:
    lib = ctypes.cdll.LoadLibrary('libX11.so.6')
    lib.XOpenDisplay.argtypes = [c_char_p]
    lib.XOpenDisplay.restype = c_void_p
    lib.XDefaultRootWindow.argtypes = [c_void_p]
    lib.XDefaultRootWindow.restype = c_ulong
    lib.XGetGeometry.argtypes = [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_int), POINTER(c_int),
                                 POINTER(c_uint), POINTER(c_uint), POINTER(c_uint), POINTER(c_uint)]
    lib.XGetGeometry.restype = c_int
    lib.XGetWindowAttributes.argtypes = [c_void_p, c_ulong, c_void_p]
    lib.XGetImage.argtypes = [c_void_p, c_ulong, c_int, c_int, c_uint, c_uint, c_ulong, c_int]
    lib.XGetImage.restype = POINTER(XImage)
    lib.XDestroyImage.argtypes = [POINTER(XImage)]
    lib.XCloseDisplay.argtypes = [c_void_p]
    lib.XTranslateCoordinates.argtypes = [c_void_p, c_ulong, c_ulong, c_int, c_int,
                                          POINTER(c_int), POINTER(c_int), POINTER(c_ulong)]

    display_name = os.environ.get('DISPLAY', '').encode() or None
    dpy = lib.XOpenDisplay(display_name)
    if not dpy:
        raise SystemExit('Cannot open X display %s' % os.environ.get('DISPLAY'))
    try:
        root = lib.XDefaultRootWindow(dpy)
        # Capture the client window; if it's tiny, grab from the root at its translated origin.
        root_x = c_int()
        root_y = c_int()
        child = c_ulong()
        lib.XTranslateCoordinates(dpy, window_id, root, 0, 0, byref(root_x), byref(root_y), byref(child))
        dummy = c_ulong()
        x = c_int()
        y = c_int()
        w = c_uint()
        h = c_uint()
        bw = c_uint()
        depth = c_uint()
        if not lib.XGetGeometry(dpy, window_id, byref(dummy), byref(x), byref(y), byref(w), byref(h), byref(bw), byref(depth)):
            raise SystemExit('XGetGeometry failed for 0x%x' % window_id)
        width, height = int(w.value), int(h.value)
        if width < 2 or height < 2:
            raise SystemExit('Window 0x%x has empty geometry %sx%s' % (window_id, width, height))
        ZPixmap = 2
        AllPlanes = 0xffffffffffffffff
        image = lib.XGetImage(dpy, window_id, 0, 0, width, height, AllPlanes, ZPixmap)
        if not image:
            # Fall back to the root window region (includes any window manager frame).
            image = lib.XGetImage(dpy, root, int(root_x.value), int(root_y.value), width, height, AllPlanes, ZPixmap)
        if not image:
            raise SystemExit('XGetImage failed for 0x%x' % window_id)
        try:
            img = image.contents
            r_shift, r_bits = _mask_shift(img.red_mask)
            g_shift, g_bits = _mask_shift(img.green_mask)
            b_shift, b_bits = _mask_shift(img.blue_mask)
            bpp = img.bits_per_pixel
            bpl = img.bytes_per_line
            raw = ctypes.string_at(img.data, bpl * img.height)
            out = bytearray(width * height * 3)

            def scale(value, bits):
                if bits >= 8:
                    return (value >> (bits - 8)) & 0xff
                if bits == 0:
                    return 0
                return (value * 255) // ((1 << bits) - 1)

            for row in range(height):
                row_off = row * bpl
                for col in range(width):
                    if bpp == 32 or bpp == 24:
                        pix_off = row_off + col * (4 if bpp == 32 else 3)
                        if img.byte_order == 0:  # LSBFirst
                            pixel = int.from_bytes(raw[pix_off:pix_off + (4 if bpp == 32 else 3)] + (b'\x00' if bpp == 24 else b''), 'little')
                        else:
                            chunk = raw[pix_off:pix_off + (4 if bpp == 32 else 3)]
                            pixel = int.from_bytes(chunk.rjust(4, b'\x00') if bpp == 24 else chunk, 'big')
                    else:
                        raise SystemExit('Unsupported bits_per_pixel %s' % bpp)
                    dst = (row * width + col) * 3
                    out[dst] = scale((pixel >> r_shift) & ((1 << r_bits) - 1), r_bits)
                    out[dst + 1] = scale((pixel >> g_shift) & ((1 << g_bits) - 1), g_bits)
                    out[dst + 2] = scale((pixel >> b_shift) & ((1 << b_bits) - 1), b_bits)
            write_png(path, width, height, bytes(out))
        finally:
            lib.XDestroyImage(image)
    finally:
        lib.XCloseDisplay(dpy)


def _pump(root, seconds=0.6):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.05)


def main() -> int:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'docs'
    dest.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.geometry('1100x720+20+20')
    app = Application(root)
    root.deiconify()
    _pump(root, 0.8)
    main_png = dest / 'screenshot.png'
    grab_window(int(root.winfo_id()), main_png)
    about = AboutDialog(root)
    about.window.geometry('+80+40')
    _pump(root, 0.8)
    about_png = dest / 'about.png'
    grab_window(int(about.window.winfo_id()), about_png)
    about.window.destroy()
    app.jobs.shutdown(wait=False)
    root.destroy()
    for path in (main_png, about_png):
        if path.stat().st_size < 1000:
            raise SystemExit('Screenshot too small: %s' % path)
        print('WROTE', path, path.stat().st_size, 'bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
