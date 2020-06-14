#!/usr/bin/env python


import argparse
import numpy
import random
import time

import colour
from PIL import Image, ImageSequence

import walle


class ImageDisplay:
    def __init__(self, driver, path, party):
        self.driver = driver
        self.image = Image.open(path)
        self.frames = []
        self.frame_idx = 0

        # Prepare frames
        orig_height, orig_width = self.image.size
        disp_height, disp_width = driver.dim()

        party_n_colors = 20
                
        if self.image.format == 'GIF' and self.image.is_animated:
            party_n_colors = self.image.n_frames
            for frame_idx, frame in enumerate(ImageSequence.Iterator(self.image)):
                hue_shift = (frame_idx / party_n_colors) % 1.0 if party else 0
                self.frames.append([[self._r(frame.resize((disp_height, disp_width), 
                                                           Image.BICUBIC).convert('RGBA').getpixel((x, y)), hue_shift)
                                     for x in range(disp_width)] for y in range(disp_height)])
                self.frame_idx += 1
            self.period = self.image.info['duration'] / 1000.  # ms to s
        elif party:
            resized_image = self.image.resize((disp_height, disp_width), Image.BICUBIC).convert('RGBA')
            self.period = 0.05
            for party_idx in range(self.party_n_colors):
                hue_shift = (frame_idx / party_n_colors) % 1.0
                self.frames.append([[self._r(resized_image.getpixel((x, y)))
                                     for x in range(disp_width)] for y in range(disp_height)], hue_shift)
        else:
            self.frames.append([[self._r(self.image.resize((disp_height, disp_width), 
                                                           Image.BICUBIC).convert('RGBA').getpixel((x, y)))
                                 for x in range(disp_width)] for y in range(disp_height)])
            self.period = 1

    def _r(self, pixel_rgba, hue_shift=0):
        alpha = pixel_rgba[3] / 255
        pixel_color = colour.Color(rgb=tuple([subpixel / 255. for subpixel in pixel_rgba[:3]]))
        pixel_color.luminance *= alpha
        pixel_color.hue = pixel_color.hue + hue_shift
        return pixel_color.rgb

    def update(self):
        self.driver.set(self.frames[self.frame_idx % len(self.frames)])
        self.frame_idx += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    parser.add_argument('image', type=str, help='Image to display')
    parser.add_argument('--party', action='store_true', help='Add hue shift to images')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    image = ImageDisplay(driver, args.image, args.party)
    period = walle.PeriodFloor(image.period)
    while True:
        image.update()
        period.sleep()
