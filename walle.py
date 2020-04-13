#!/usr/bin/env python

import argparse
import collections
import copy
import re
import select
import socket
import spidev
import struct
import time

DEFAULT_NUM_ROWS = 10
DEFAULT_NUM_COLS = 10

DEFAULT_UDP_SERVER_PORT = 4513

def all_off_matrix(dim):
    # expected to return a copy
    return [[(0., 0., 0.) for _ in range(dim[0])] for _ in range(dim[1])]

def all_on_matrix(dim):
    # expected to return a copy
    return [[(1., 1., 1.) for _ in range(dim[0])] for _ in range(dim[1])]

def _get_dim(matrix):
    assert len(matrix) > 0
    assert len(set(len(row) for row in matrix)) == 1
    return len(matrix), len(matrix[0])

def _pack_udp(matrix, msg_id):
    # Verify all rows are the same size
    num_rows, num_cols = _get_dim(matrix)
    chs = (ch for row in matrix for color in row for ch in color)
    data = struct.pack('>III{}f'.format(3 * num_rows * num_cols), msg_id, num_rows, num_cols, *chs)
    assert len(data) == 12 + 4 * 3 * num_rows * num_cols
    return data

def _unpack_udp(data):
    num_chs = int((len(data) - 3 * 4) / 4) # if there's truncation here, it will show up in unpack()
    if num_chs <= 0:
        raise RuntimeError('invalid packet size {}'.format(len(data)))
    try:
        msg_id, num_rows, num_cols, *chs = struct.unpack('>III{}f'.format(num_chs), data)
    except struct.error as e:
        raise RuntimeError(str(e))
    if num_chs != 3 * num_rows * num_cols:
        raise RuntimeError('received dimensions {}x{} do not match channel count'.format(
            num_rows, num_cols, num_chs))
    if min(chs) < 0 or max(chs) > 1.0:
        raise RuntimeError('received channels contain values out of bounds')
    colors = [tuple(chs[i:i + 3]) for i in range(0, len(chs), 3)]
    matrix = [colors[i:i + num_cols] for i in range(0, len(colors), num_cols)]
    return matrix, msg_id

def create_display(target):
    if target == 'spi':
        return LocalLedDisplay()
    else:
        return UdpLedDisplay(target)

class LocalLedDisplay:
    def __init__(self, bus=0, index=0, num_rows=DEFAULT_NUM_ROWS, num_cols=DEFAULT_NUM_COLS, sclk_hz=250000):
        """
        250 KHz SPI should be sufficient to transfer 24 bits of information to 100 LEDs in ~0.01
        seconds. Some occasional glitching was observed on the real display at 1 MHz.
        """
        print('Using SPI bus {} index {}'.format(bus, index))
        self._spi = spidev.SpiDev()
        self._spi.open(bus, index)
        self._spi.lsbfirst = False
        self._spi.max_speed_hz = sclk_hz
        self._spi.mode = 0b00

        self._dim = (num_rows, num_cols)

        self._current_matrix = None
        self.set(all_off_matrix(self.dim()))

    def set(self, matrix):
        # note: it's important that _current_matrix becomes a copy here. store it before gamma
        # correction.
        assert _get_dim(matrix) == self._dim
        self._current_matrix = copy.deepcopy(matrix)
        self._spi.xfer(self._flatten(self._gamma_corrected(matrix)))

    def get(self):
        return self._current_matrix

    def dim(self):
        return tuple(self._dim)

    def _gamma_corrected(self, matrix):
        return [[tuple(ch ** 2.3 for ch in color) for color in row] for row in matrix]

    def _flatten(self, matrix):
        # rows are physically wired low to high, so row order must be reversed. every other row must
        # also be internally reversed to account for chain snaking.
        snaked_rows = (row if i % 2 == 0 else reversed(row)
                        for i, row in enumerate(reversed(matrix)))
        flattened_rgb = [ch for row in snaked_rows for color in row for ch in color]

        # convert to 8-bit channels, but verify ranges first
        assert all(ch >= 0 and ch <= 1.0 for ch in flattened_rgb)
        flattened_rgb8 = [min(int(ch * 256), 255) for ch in flattened_rgb]

        assert len(flattened_rgb8) == 3 * self._dim[0] * self._dim[1]
        return flattened_rgb8

class UdpLedDisplay:
    def __init__(self, host, port=DEFAULT_UDP_SERVER_PORT, num_rows=DEFAULT_NUM_ROWS,
                 num_cols=DEFAULT_NUM_COLS, timeout=0.2):
        """
        relatively long timeout gives the servers's buffers a break if they are falling behind
        """
        print('Using UDP server {}:{} with timeout {}'.format(host, port, timeout))
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._host = host
        self._port = port
        self._dim = (num_rows, num_cols)
        self._timeout = timeout
        self._msg_id = 0

        # track past outcomes for timeout tracking
        self._recent_failures = collections.deque()
        self._num_recent_failures = 0

    def set(self, matrix):
        # catch specifically timeouts for later
        failed = False
        try:
            self._set(matrix)
        except TimeoutError:
            failed = True
            print('timeout!')

        # record the new outcome. if the recent outcome history has grown long enough, start
        # retiring old history. keep the memo'd count up to date.
        self._recent_failures.append(failed)
        self._num_recent_failures += failed
        while len(self._recent_failures) > 1000:
            self._num_recent_failures -= self._recent_failures[0]
            self._recent_failures.popleft()
        assert self._num_recent_failures >= 0

        # if the number of timeouts is too high now, re-raise the timeout. otherwise, the timeout is
        # just swallowed
        max_recent_timeouts = 10
        if self._num_recent_failures > max_recent_timeouts:
            print('too many timeouts!')
            raise TimeoutError('Too many timeouts ({} in last {} transactions)'.format(
                self._num_recent_failures, len(self._recent_failures)))

    def _set(self, matrix):
        """
        Idea here is that after set() returns, the display has observed the update. This keeps
        semantics with direct driver set(), naturally throttles calls to set(), provides an answer
        to how to receive replies asynchronously (just don't, do it synchronously), allows the
        sender to directly bound display latency, and keeps the error-handling at the sender.
        """
        # Verify the data matches our own idea of the display dimensions.
        assert _get_dim(matrix) == self._dim

        # Send the data
        tx_msg_id =  self._msg_id
        self._msg_id = (self._msg_id + 1) % 2**32
        tx = _pack_udp(matrix, tx_msg_id)
        self.socket.sendto(tx, (self._host, self._port))

        # Wait for the acknowledgement
        start = time.time()
        time_left = self._timeout
        acked = False
        while time_left >= 0 and not acked:
            readers, _, _ = select.select([self.socket], [], [], time_left)
            if self.socket in readers:
                rx, _ = self.socket.recvfrom(4096) # should return immediately
                try:
                    rx_matrix, rx_msg_id = _unpack_udp(rx)
                except RuntimeError as e:
                    pass
                else:
                    # if message ID does not match, ignore this message. but if dimensions don't
                    # match, that's an error. it's overkill to verify contents.
                    if rx_msg_id == tx_msg_id:
                        rx_dim = _get_dim(rx_matrix)
                        if rx_dim != self._dim:
                            raise RuntimeError('Remote display has unexpected dimensions '
                                               '{}x{}'.format(*rx_dim))
                        acked = True
            time_left = self._timeout - (time.time() - start)

        # if we didn't get an ACK, throw TimeoutError
        if not acked:
            raise TimeoutError('did not receive ack for msg id {}'.format(tx_msg_id))

    def get(self):
        """
        Like set(), this interactively fetches the display and blocks until completion. See notes
        above.
        """
        raise RuntimeError('not implemented')

    def dim(self):
        return tuple(self._dim)

class _UdpHandler(socketserver.BaseRequestHandler):
    def handle(self):
        # if unpacking the message fails, return
        try:
            matrix, msg_id = _unpack_udp(self.request[0])
        except RuntimeError as e:
            print('discarded bogus request: {}'.format(e))
            return

        # if the dimensions are bogus, return
        driver = self.server.driver
        if _get_dim(matrix) != driver.dim():
            return

        # set the new data to the display
        try:
            driver.set(matrix)
        except TimeoutError as e:
            # propagate any timeout
            print('set() timed out')
            return

        # acknowledge the request
        ack = _pack_udp(driver.get(), msg_id)
        self.request[1].sendto(ack, self.client_address)

class _UdpLedDisplayServer:
    """
    This was originally implemented as a synchronous socketserver.UDPServer, but became concerned
    about requests backing up in OS buffers. This version only serves the most recent request in the
    RX buffers.
    """
    def __init__(self, host_port, driver):
        self._driver = driver
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(host_port)

    def serve_forever():
        while True:
            # wait for the socket to have pending data, then poll for all pending messages.
            readers, _ _ = select.select([self._socket], [], [])
            msgs = []
            while self._socket in readers:
                msgs.append(self._socket.recvfrom(4096))
                readers, _ _ = select.select([self._socket], [], [], 0)
            assert not readers

            # process messages back-to-front until a valid one is found.
            msg_found = False
            for msg in reversed(msgs):
                # if a message has already been processed, then the rest of the (earlier) messages
                # should be skipped
                data, client_addr = msg
                if msg_found:
                    print('skipping message from {}:{}'.format(*client_addr))
                    continue

                # if unpacking the message fails, discard
                try:
                    matrix, msg_id = _unpack_udp(msg)
                except RuntimeError as e:
                    print('discarding malformed message: {}'.format(e))
                    continue

                # if the dimensions are wrong, discard
                dim = _get_dim(matrix)
                if dim != driver.dim():
                    print('discarded request with incorrect dimensions {}x{}'.format(*dim))
                    continue

                # set the new data to the display. if it times out, treat it the same as a discard
                try:
                    driver.set(matrix)
                except TimeoutError as e:
                    print('setting the display timed out')
                    continue

                # acknowledge the request, and signal the remaining messages to be skipped
                ack = _pack_udp(self.driver.get(), msg_id)
                self._socket.sendto(ack, client_addr)
                msg_found = True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', type=str, help='The display to connect to')
    parser.add_argument('--listen_port', type=int, default=4513, help='UDP server listen port')
    args = parser.parse_args()

    driver = create_display(args.target)
    server = UdpLedDisplayServer(('', args.listen_port), driver)
    print('Listening on :{}'.format(server.server_address[1]))
    server.serve_forever()
