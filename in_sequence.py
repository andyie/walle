#!/usr/bin/env python

import argparse
import walle
import time

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    args = parser.parse_args()

    walle.log.info('should shine each color for each led left-to-right for each row top-to-bottom')
    driver = walle.create_display(args.target)
    while True:
        rows, cols = driver.dim()
        for row in range(rows):
            for col in range(cols):
                for ch in range(3):
                    matrix = walle.all_off_matrix(driver.dim())
                    matrix[row][col] = tuple(1 if i == ch else 0 for i in range(3))
                    driver.set(matrix)
                    time.sleep(0.05)
