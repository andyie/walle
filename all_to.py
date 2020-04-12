#!/usr/bin/python

import argparse
import walle

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('red', type=float, help='Red component 0-1')
    parser.add_argument('green', type=float, help='Green component 0-1')
    parser.add_argument('blue', type=float, help='Blue component 0-1')
    args = parser.parse_args()

    def valid(v):
        return v >= 0. and v <= 1.
    assert valid(args.red) and valid(args.green) and valid(args.blue)

    w = walle.WallE()
    w.update([[Color(r=args.red, g=args.green, b=args.blue)] * self._num_cols] * self._num_rows)
