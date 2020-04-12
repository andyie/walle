#!/usr/bin/python

import walle
import time

if __name__ == '__main__':
    print('Should shine each color left-to-right in sequence for each row top-to-bottom')
    w = walle.WallE()
    while True:
        rows, cols = w.dim()
        for row in range(rows):
            for col in range(cols):
                for ch in range(3):
                    matrix = w.all_off_matrix()
                    matrix[row][col] = walle.Color(*(1 if i == ch else 0 for i in range(3)))
                    w.set(matrix)
                    time.sleep(0.05)
