#!/usr/bin/env python


import argparse
import numpy
import random
import time

from PIL import Image, ImageSequence

import walle


class ImageDisplay:
    def __init__(self, driver, path):
        self.driver = driver
        self.image = Image.open(path)
        self.frames = []
        self.frame_idx = 0

        # Prepare frames
        orig_height, orig_width = self.image.size
        disp_height, disp_width = driver.dim()
        factor_height = orig_height // disp_height + 1
        factor_width = orig_width // disp_width + 1
                
        if self.image.is_animated:
            for frame in ImageSequence.Iterator(self.image):
                self.frames.append([[self._r(frame.resize((disp_height, disp_width), 
                                                           Image.BICUBIC).convert('RGBA').getpixel((x, y)))
                                     for x in range(disp_width)] for y in range(disp_height)])
            self.period = self.image.info['duration'] / 1000.  # ms to s
        else:
            self.frames.append([[self._r(self.image.resize((disp_height, disp_width), 
                                                           Image.BICUBIC).convert('RGBA').getpixel((x, y)))
                                 for x in range(disp_width)] for y in range(disp_height)])
            self.period = 1

    def _r(self, pixel):
        alpha = pixel[3] / 255
        return tuple([alpha * subpixel / 255. for subpixel in pixel[:3]])

    def update(self):
        self.driver.set(self.frames[self.frame_idx % len(self.frames)])
        self.frame_idx += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    parser.add_argument('image', type=str, help='Image to display')
    args = parser.parse_args()

    driver = walle.create_display(args.target)
    image = ImageDisplay(driver, args.image)
    period = walle.PeriodFloor(image.period)
    while True:
        image.update()
        period.sleep()
