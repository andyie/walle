#!/usr/bin/python

import argparse
import walle

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('r', type=float, help='Red component 0-1')
    parser.add_argument('g', type=float, help='Green component 0-1')
    parser.add_argument('b', type=float, help='Blue component 0-1')
    args = parser.parse_args()

    def valid(v):
        return v >= 0. and v <= 1.
    assert valid(args.r) and valid(args.g) and valid(args.b)

    w = walle.WallE()
    w.set([[walle.Color(r=args.r, g=args.g, b=args.b)] * w.get_num_cols()] * w.get_num_rows())
