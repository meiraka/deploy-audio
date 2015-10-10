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


class App(object):

    """RotarySwitch for mpd control."""

    def __init__(self, prev, play, next, logger=None):
        """Open gpio for prev/play/next button."""
        self.logger = logger if logger else logging
        self.logger.info("start app")
        self._values = {}
        self._prev = prev
        self._values[self._prev] = '0'
        self._play = play
        self._values[self._play] = '0'
        self._next = next
        self._values[self._next] = '0'
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)

    def exit(self, signum, frame):
        """display of when exit app."""
        self.logger.info("stop app")
        sys.exit(0)

    def _is_changed(self, fo):
        """Check file data is changed."""
        fo.seek(0)
        new = fo.read().strip()
        if self._values[fo] != new:
            self._values[fo] = new
            return True
        else:
            return False

    def run(self):
        """Wait gpio value is changed."""
        epoll = select.epoll()
        epoll.register(self._prev,
                       select.EPOLLIN | select.EPOLLET)
        epoll.register(self._play,
                       select.EPOLLIN | select.EPOLLET)
        epoll.register(self._next,
                       select.EPOLLIN | select.EPOLLET)
        try:
            while True:
                try:
                    for fileno, event in epoll.poll():
                        if fileno == self._prev.fileno():
                            if self._is_changed(self._prev):
                                # call prev if gpio#prev == '1'
                                cmd = ('prev'
                                       if self._values[self._prev] == '1'
                                       else 'pause')
                                subprocess.check_output(
                                    ['/usr/bin/mpc', cmd])
                                time.sleep(0.2)
                        if fileno == self._play.fileno():
                            if self._is_changed(self._play):
                                # call play if gpio#play == '1'
                                cmd = ('play'
                                       if self._values[self._play] == '1'
                                       else 'pause')
                                subprocess.check_output(
                                    ['/usr/bin/mpc', cmd])
                        if fileno == self._next.fileno():
                            if self._is_changed(self._next):
                                # call next if gpio#next == '1'
                                # do not pause because
                                # gpio#play = '1' if gpio#next == '1'
                                if self._values[self._next] == '1':
                                    subprocess.check_output(
                                        ['/usr/bin/mpc', 'next'])
                                time.sleep(0.2)
                except subprocess.CalledProcessError:
                    time.sleep(1)
        finally:
            epoll.unregister(self._prev)
            epoll.unregister(self._play)
            epoll.unregister(self._next)


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
    try:
        # prev_album = gpio_open(22, edge='both')
        prev = gpio_open(10, edge='both')
        play = gpio_open(9, edge='both')
        next = gpio_open(11, edge='both')
        # next_album = gpio_open(23, edge='both')
        sw = App(prev, play, next, logger)
        sw.run()
        # sw.run_poll()
    except Exception, err:
        logger.critical("app exit with: %s" % str(err))
        logger.critical(traceback.format_exc())

if __name__ == '__main__':
    main()
