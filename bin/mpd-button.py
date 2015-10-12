#!/usr/bin/python2

"""RotarySwitch for mpd control."""


import os
import select
import subprocess
import time
import logging
import traceback
import threading
import signal
import sys


class MPD(threading.Thread):

    """ mpd controller."""

    def __init__(self):
        """Initialize thread."""
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.playlist = []
        self.start()

    def run(self):
        """Get playlist."""
        while True:
            try:
                out = subprocess.check_output(
                    ['/usr/bin/mpc', 'playlist', '-f', '%album%'])
                self.playlist = [{'album': i} for i in out.split()]

                subprocess.check_output(
                    ['/usr/bin/mpc', 'idle', 'playlist'])
            except subprocess.CalledProcessError:
                time.sleep(1)

    def prev_album(self):
        """Play prev album song."""
        pos = self._position()
        current_album = self.playlist[pos]['album']
        use_prev_album = False
        prev_album = None
        for prev_count, song in enumerate(reversed(self.playlist[:pos])):
            if prev_count == 0 and not current_album == song['album']:
                use_prev_album = True
                continue
            if not use_prev_album:
                if not current_album == song['album']:
                    subprocess.check_output(
                        ['/usr/bin/mpc', 'play',
                         str(pos - prev_count + 1)])
                    return
            else:
                if prev_album is None:
                    if not current_album == song['album']:
                        prev_album = song['album']
                        print prev_album
                else:
                    if not prev_album == song['album']:
                        subprocess.check_output(
                            ['/usr/bin/mpc', 'play',
                             str(pos - prev_count + 1)])
                        return
        subprocess.check_output(
            ['/usr/bin/mpc', 'play', '1'])

    def prev(self):
        """Play prev song."""
        subprocess.check_output(
            ['/usr/bin/mpc', 'prev'])

    def pause(self):
        """Pause song."""
        subprocess.check_output(
            ['/usr/bin/mpc', 'pause'])

    def play(self):
        """Play song."""
        subprocess.check_output(
            ['/usr/bin/mpc', 'play'])

    def next(self):
        """Play next song."""
        subprocess.check_output(
            ['/usr/bin/mpc', 'next'])

    def next_album(self):
        """Play prev album song."""
        pos = self._position()
        current_album = self.playlist[pos]['album']
        for next_count, song in enumerate(self.playlist[pos:]):
            if not current_album == song['album']:
                subprocess.check_output(
                    ['/usr/bin/mpc', 'play', str(pos + next_count + 1)])
                return
        subprocess.check_output(
            ['/usr/bin/mpc', 'play', '1'])

    def _position(self):
        """Return playlist playing position."""
        out = subprocess.check_output(
            ['/usr/bin/mpc', '-f', '%position%'])
        return int(out.splitlines()[0]) - 1


class App(object):

    """RotarySwitch for mpd control."""

    def __init__(self, prev_album, prev, pause, play, next, next_album,
                 logger=None):
        """Open gpio for prev/play/next button."""
        self.mpd = MPD()
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
