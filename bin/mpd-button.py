#!/usr/bin/python2

"""RotarySwitch for mpd control."""


import os
import select
import subprocess
import time
import logging
import traceback
import signal
import sys


class MPD():

    """ mpd controller."""

    def __init__(self, logger):
        """Initialize thread."""
        self.logger = logger if logger else logging
        self.playlist = []

    def prev_album(self):
        """Play prev album song."""
        self.logger.info("prev album")
        playlist = self.get_playlist()
        pos = self.get_position()
        current_album = playlist[pos]['album']
        self.logger.info("current album: %s" % current_album)
        for prev_count, song in enumerate(reversed(playlist[:pos])):
            if prev_count == 0 and not current_album == song['album']:
                self.logger.info("detect current song is head in album.")
                current_album = song['album']
                self.logger.info("set current album: %s" % current_album)
                continue
            if not current_album == song['album']:
                new_pos = pos - prev_count + 1
                subprocess.check_output(
                    ['/usr/bin/mpc', 'play', str(new_pos)])
                self.logger.info("play %i" % new_pos)
                return
        subprocess.check_output(
            ['/usr/bin/mpc', 'play', '1'])

    def prev(self):
        """Play prev song."""
        self.logger.info("prev")
        subprocess.check_output(
            ['/usr/bin/mpc', 'prev'])

    def pause(self):
        """Pause song."""
        self.logger.info("pause")
        subprocess.check_output(
            ['/usr/bin/mpc', 'pause'])

    def play(self):
        """Play song."""
        self.logger.info("play")
        subprocess.check_output(
            ['/usr/bin/mpc', 'play'])

    def next(self):
        """Play next song."""
        self.logger.info("next")
        subprocess.check_output(
            ['/usr/bin/mpc', 'next'])

    def next_album(self):
        """Play prev album song."""
        self.logger.info("next album")
        playlist = self.get_playlist()
        pos = self.get_position()
        current_album = playlist[pos]['album']
        self.logger.info("current album: %s" % current_album)
        for next_count, song in enumerate(playlist[pos:]):
            if not current_album == song['album']:
                self.logger.info("new album: %s" % song['album'])
                new_pos = pos + next_count + 1
                subprocess.check_output(
                    ['/usr/bin/mpc', 'play', str(new_pos)])
                self.logger.info("play %i" % new_pos)
                return
        subprocess.check_output(
            ['/usr/bin/mpc', 'play', '1'])

    def get_playlist(self):
        """Return playlist."""
        out = subprocess.check_output(
            ['/usr/bin/mpc', 'playlist', '-f', '%album%'])
        return [{'album': i} for i in out.splitlines()]

    def get_position(self):
        """Return playlist playing position."""
        out = subprocess.check_output(
            ['/usr/bin/mpc', '-f', '%position%'])
        return int(out.splitlines()[0]) - 1


class App(object):

    """RotarySwitch for mpd control."""

    def __init__(self, prev_album, prev, pause, play, next, next_album,
                 logger=None):
        """Open gpio for prev/play/next button."""
        self.mpd = MPD(logger)
        self.logger = logger if logger else logging
        self.logger.info("start app")
        self._prev_album = prev_album
        self._prev = prev
        self._pause = pause
        self._play = play
        self._next = next
        self._next_album = next_album
        self._last = self._pause
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)

    def exit(self, signum, frame):
        """display of when exit app."""
        self.logger.info("stop app")
        sys.exit(0)

    def _gpio_read(self, f):
        """read gpio value."""
        f.seek(0)
        out = f.read().strip()
        return out

    def run(self):
        """Wait gpio value is changed."""
        epoll = select.epoll()
        epoll.register(self._prev_album,
                       select.EPOLLIN | select.EPOLLET)
        epoll.register(self._prev,
                       select.EPOLLIN | select.EPOLLET)
        epoll.register(self._pause,
                       select.EPOLLIN | select.EPOLLET)
        epoll.register(self._play,
                       select.EPOLLIN | select.EPOLLET)
        epoll.register(self._next,
                       select.EPOLLIN | select.EPOLLET)
        epoll.register(self._next_album,
                       select.EPOLLIN | select.EPOLLET)
        try:
            while True:
                try:
                    time.sleep(0.1)
                    for fileno, event in epoll.poll():
                        if self._gpio_read(self._prev_album) == '1':
                            if not self._last == self._prev_album:
                                self.mpd.prev_album()
                            self._last = self._prev_album
                        if self._gpio_read(self._prev) == '1':
                            if self._last not in [self._prev_album,
                                                  self._prev]:
                                self.mpd.prev()
                            self._last = self._prev
                        if self._gpio_read(self._pause) == '1':
                            if (self._last not in [self._prev,
                                                   self._prev_album]):
                                self.mpd.pause()
                            self._last = self._pause
                        if self._gpio_read(self._play) == '1':
                            self.mpd.play()
                            self._last = self._play
                        if self._gpio_read(self._next_album) == '1':
                            if not self._last == self._next_album:
                                self.mpd.next_album()
                            self._last = self._next_album
                        if self._gpio_read(self._next) == '1':
                            if self._last not in [self._next,
                                                  self._next_album]:
                                self.mpd.next()
                            self._last = self._next

                except subprocess.CalledProcessError:
                    time.sleep(1)
                except IndexError:
                    time.sleep(1)
        finally:
            epoll.unregister(self._prev_album)
            epoll.unregister(self._prev)
            epoll.unregister(self._pause)
            epoll.unregister(self._play)
            epoll.unregister(self._next)
            epoll.unregister(self._next_album)


def gpio_open(port, mode='r', register='', edge='none', active_low='0'):
    """Open gpio file."""
    if mode not in ['r', 'w']:
        raise Exception('unimplemented mode: %s' % mode)
    if edge not in ['none', 'rising', 'falling', 'both']:
        raise Exception('rtfm')
    port = str(port)
    if os.path.exists('/sys/class/gpio/gpio%s' % port):
        with open('/sys/class/gpio/unexport', 'w') as f:
            f.write(port)
    with open('/sys/class/gpio/export', 'w') as f:
        f.write(port)
    if mode == 'r':
        with open('/sys/class/gpio/gpio%s/direction' % port, 'w') as f:
            f.write('in')
        if register:
            with open('/sys/class/gpio/gpio%s/direction' % port, 'w') as f:
                f.write(register)
    elif mode == 'w':
        with open('/sys/class/gpio/gpio%s/direction' % port, 'w') as f:
            f.write('out')

    with open('/sys/class/gpio/gpio%s/edge' % port, 'w') as f:
        f.write(edge)
    with open('/sys/class/gpio/gpio%s/active_low' % port, 'w') as f:
        f.write(active_low)

    return open('/sys/class/gpio/gpio%s/value' % port, mode)


def main():
    """Run app mainloop."""
    logging.basicConfig(
        filename='/var/log/mpd-button.log',
        format='[%(levelname)s] %(asctime)s [%(name)s] %(message)s',
        datefmt='%Y/%m/%d %H:%M:%S',
        level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    prev_album = gpio_open(22, edge='rising')
    prev = gpio_open(10, edge='rising')
    pause = gpio_open(9, edge='rising')
    play = gpio_open(11, edge='rising')
    next = gpio_open(23, edge='rising')
    next_album = gpio_open(24, edge='rising')
    sw = App(prev_album, prev, pause, play, next, next_album, logger)
    sw.run()

if __name__ == '__main__':
    main()
