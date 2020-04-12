#!/usr/bin/env python

import walle
import time

if __name__ == '__main__':
    print('Should shine each color left-to-right in sequence for each row top-to-bottom')
    driver = walle.LedDisplayDriver()
    while True:
        rows, cols = driver.dim()
        for row in range(rows):
            for col in range(cols):
                for ch in range(3):
                    matrix = walle.all_off_matrix(driver.dim())
                    matrix[row][col] = walle.Color(*(1 if i == ch else 0 for i in range(3)))
                    driver.set(matrix)
                    time.sleep(0.05)
