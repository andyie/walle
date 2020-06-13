#!/usr/bin/env python


import argparse
import numpy
import random
import time

from PIL import Image, ImageSequence

import walle


def _r(pixel):
    return tuple([subpixel/255. for subpixel in pixel])


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
                self.frames.append([[_r(frame.convert('RGB').reduce((factor_height, factor_width)).getpixel((x, y))) for x in range(disp_width)] for y in range(disp_height)])
        else:
            self.frames.append([[_r(self.image.convert('RGB').reduce((factor_height, factor_width)).getpixel((x, y))) for x in range(disp_width)] for y in range(disp_height)])

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
    period = walle.PeriodFloor(0.05)
    while True:
        image.update()
        period.sleep()
