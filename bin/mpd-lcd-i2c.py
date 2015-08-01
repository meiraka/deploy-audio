#!/usr/bin/python2

"""Show mpd status to i2c lcd display."""


import copy
import os
import time
import threading
import subprocess
import re
import Queue
import logging
import traceback

import smbus


I2C_BUS = 1
I2C_ADDRESS = 0x3c
I2C_DDRAM_ADDRESS = (0x00, 0x20)
I2C_DISPLAY_WIDTH = 16


class App(threading.Thread):

    """Show MPD song/player information to I2C display."""

    DISPLAY_SUSPEND_SEC = 10
    POLL_SEC = 0.2

    def __init__(self, logger=None):
        """Initialize mpd client and i2c display."""
        self.logger = logger if logger else logging
        self.logger.info("start app")
        threading.Thread.__init__(self)
        self.setDaemon(True)
        # initialize display
        self.display = I2CDisplay(I2C_BUS, I2C_ADDRESS,
                                  I2C_DDRAM_ADDRESS, I2C_DISPLAY_WIDTH,
                                  self.logger)
        self.display.set_brightness(0xFF)

        # initialize mpd client
        self.mpd = MPDStatus(self.logger)
        # register functions to mpd event
        self.mpd.bind(self.mpd.EVENT_PAUSE, self.event_suspend_display)
        self.mpd.bind(self.mpd.EVENT_STOP, self.event_suspend_display)
        self.mpd.bind(self.mpd.EVENT_PLAY, self.event_cancel_suspend_display)
        self.mpd.bind(self.mpd.EVENT_PLAY, self.event_update_song)
        self.mpd.bind(self.mpd.EVENT_CHANGE, self.event_update_song)
        self.mpd.bind(self.mpd.EVENT_SERVER_DOWN, self.event_show_error)
        self.mpd.bind(self.mpd.EVENT_SERVER_HANGUP, self.event_show_error)

        self.mpd.start()

        # poll event functions(used by self.run())
        self._timer = [self.timer_update_time,
                       self.timer_display_suspend,
                       self.timer_scroll]

        self._queue = Queue.Queue()
        self._display_suspend_time = -1  # < 0 means disable
        self._line2_hold_time = -1  # < 0 means disable
        self._queue.put(self.startup_message)

    def startup_message(self):
        """Show startup message."""
        self.display.write('RuneAudio'.center(self.display.width), line=0)
        time.sleep(2)

    def timer_update_time(self):
        """Update bottom line playing time.

        * check status is playing
        * check _line2_hold_time is expired
        """
        if not self.mpd.player()['status'] == 'playing':
            return
        if self._line2_hold_time > time.time():
            return
        if not self.display.is_on():
            self.display.on()
        song = self.mpd.song()
        if 'time_elapsed' not in song:
            return
        now = song['time_elapsed']
        # left_data = self.make_progressbar_bordered(now, song['length'], 10)
        left_data = list(self.make_progressbar_simple(now, song['length'], 10))
        bottom = ' %02i:%02i' % (now / 60, now % 60)
        right_data = map(ord, list(bottom))
        self.display.write_raw(left_data + right_data, line=1)

    def timer_display_suspend(self):
        """Suspend display if expire."""
        if self._display_suspend_time < 0:
            return
        if self._display_suspend_time < time.time() and self.display.is_on():
            self.display.off()

    def timer_scroll(self):
        """Scroll line1 text."""
        if self.display.is_on():
            self.display.shift(0)

    def event_update_song(self, event=''):
        """Update playing song string.

        * set track/title/album to top line.
        * set artist to bottom line.
        """
        def update_title():
            if not self.display.is_on():
                self.display.on()
            top = '{title} / {album} #{track:0>2}'.format(**self.mpd.song())
            self.display.write(
                kakasi(top).ljust(self.display.width).upper(), line=0)
            bottom = '{artist}'.format(**self.mpd.song())
            self.display.write(
                kakasi(bottom).center(self.display.width).upper(), line=1)
            # freeze line2 in 4 seconds
            self._line2_hold_time = time.time() + 4
            # extend display suspend time
            if self._display_suspend_time > 0:
                self._display_suspend_time = (time.time() +
                                              self.DISPLAY_SUSPEND_SEC)
        self._queue.put(update_title)

    def event_suspend_display(self, event):
        """Suspend display if paused/stopped."""
        if event not in [self.mpd.EVENT_PAUSE, self.mpd.EVENT_STOP]:
            return

        def show_message():
            self.display.write(
                event.center(self.display.width).upper(), line=1)
            self._display_suspend_time = time.time() + self.DISPLAY_SUSPEND_SEC
        self._queue.put(show_message)

    def event_cancel_suspend_display(self, event):
        """Clear display suspend time."""
        self._display_suspend_time = -1

    def event_show_error(self, event):
        """Show server error to display."""
        self.event_cancel_suspend_display(event)

        def show_message():
            self.display.write(
                event.center(self.display.width).upper(), line=1)
        self._queue.put(show_message)

    def run(self):
        """Kick timer functions."""
        while True:
            time.sleep(self.POLL_SEC)
            for func in self._timer:
                self._queue.put(func)

    def main(self):
        """App mainloop."""
        self.start()
        self.display.on()
        while True:
            try:
                func = self._queue.get(block=True)
                func()
            except Exception, err:
                logger.critical(traceback.format_exc())
                logger.critical(
                    "unexpect exception in App mainloop: %s" % str(err))
                time.sleep(1)

    def make_progressbar_simple(self, time_elapsed, length, width):
        """Make progressbar char in display cgram."""
        char_fill = 0
        char_prog = 1
        char_empty = 2
        char_dot_width = 5

        def bar(progress):
            """Make boxed progress bar."""
            depth = 0b11111 << (5 - progress) & 0b11111
            for y in xrange(8):
                if y in [5, 6]:
                    yield depth
                else:
                    yield 0b00000

        dot_length = char_dot_width * width
        dot_elapsed = dot_length * time_elapsed / length

        change_pos = dot_elapsed / char_dot_width
        self.display.set_char(
            char_fill, bar(char_dot_width))
        self.display.set_char(
            char_prog, bar(dot_elapsed % char_dot_width))
        self.display.set_char(
            char_empty, bar(0))
        for i in xrange(width):
            if i < change_pos:
                yield char_fill
            elif i == change_pos:
                yield char_prog
            else:
                yield char_empty

    def make_progressbar_bordered(self, time_elapsed, length, width):
        """Make progressbar char in display cgram."""
        char_left = 0
        char_centre = 1
        char_right = 2
        char_centre_fill = 3
        char_centre_empty = 4
        char_dot_width = 5
        left_dot_width = 3

        def left_box(bar_data):
            """Make left mask."""
            for y, bar_line in enumerate(bar_data):
                if y in [2, 6]:
                    yield 0b11111
                elif y in [3, 5]:
                    yield 0b10000
                elif y == 4:
                    yield (0b10000 | bar_line) & 0b10111
                else:
                    yield 0b00000

        centre_dot_width = 5

        def centre_box(bar_data):
            """Make centre mask."""
            for y, bar_line in enumerate(bar_data):
                if y in [2, 6]:
                    yield 0b11111
                elif y == 4:
                    yield bar_line
                else:
                    yield 0b00000

        right_dot_width = 3

        def right_box(bar_data):
            """Make right mask."""
            for y, bar_line in enumerate(bar_data):
                if y in [2, 6]:
                    yield 0b11111
                elif y in [3, 5]:
                    yield 0b00001
                elif y == 4:
                    yield (0b00001 | bar_line) & 0b11101
                else:
                    yield 0b00000

        def bar(progress):
            """Make boxed progress bar."""
            depth = 0b11111 << (5 - progress) & 0b11111
            for y in xrange(8):
                yield depth

        dot_length = (
            left_dot_width + right_dot_width + centre_dot_width * (width-2))
        dot_elapsed = dot_length * time_elapsed / length
        if dot_elapsed <= left_dot_width:
            self.display.set_char(
                0, left_box(bar(char_dot_width-left_dot_width+dot_elapsed)))
            self.display.set_char(1, centre_box(bar(0)))
            self.display.set_char(2, right_box(bar(0)))
            return [char_left] + [char_centre] * (width-2) + [char_right]
        elif dot_elapsed <= centre_dot_width * (width-2) + left_dot_width:
            centre_total_width = dot_elapsed - left_dot_width
            change_pos = centre_total_width / char_dot_width
            centre_str = []
            for i in xrange(width-2):
                if i < change_pos:
                    centre_str.append(char_centre_fill)
                elif i == change_pos:
                    centre_str.append(char_centre)
                else:
                    centre_str.append(char_centre_empty)
            self.display.set_char(
                char_left, left_box(bar(char_dot_width)))
            self.display.set_char(
                char_centre,
                centre_box(bar(centre_total_width % char_dot_width)))
            self.display.set_char(
                char_right, right_box(bar(0)))
            self.display.set_char(
                char_centre_fill, centre_box(bar(char_dot_width)))
            self.display.set_char(
                char_centre_empty, centre_box(bar(0)))
            return [char_left] + centre_str + [char_right]
        else:
            self.display.set_char(
                char_left, left_box(bar(char_dot_width)))
            self.display.set_char(
                char_centre, centre_box(bar(char_dot_width)))
            self.display.set_char(
                char_right,
                right_box(bar(right_dot_width - dot_length + dot_elapsed)))
            return [char_left] + [char_centre] * (width-2) + [char_right]


class MPDStatus(threading.Thread):

    """Get mpd song data."""

    EVENT_STOP = 'stopped'
    EVENT_PLAY = 'playing'
    EVENT_PAUSE = 'paused'
    EVENT_CHANGE = 'changed'
    EVENT_SERVER_DOWN = 'server down'
    EVENT_SERVER_WAKEUP = 'server wakeup'
    EVENT_SERVER_HANGUP = 'server hang-up'

    def __init__(self, logger=None):
        """Init status cache data."""
        self.logger = logger if logger else logging
        self._updatetime = time.time()
        self.fetch_data = ['artist', 'title', 'track', 'album']
        self._song = {}
        self._player = {}
        self._player['status'] = 'playing'
        self.player_settings = {}
        self.playlist_pos = 0
        self.playlist_size = 0
        self.current_time = 0
        self.time = 0
        self._callbacks = {}
        self._mpd_isalive = False
        threading.Thread.__init__(self)
        self.setDaemon(True)

    def bind(self, event, callback):
        """Set function for each events."""
        self._callbacks.setdefault(event, []).append(callback)

    def call(self, event):
        """Kick binded functions for given event."""
        if event in self._callbacks:
            for callback in self._callbacks[event]:
                callback(event)

    def run(self):
        """Update mpd song data."""
        while True:
            try:
                events = []
                fetch_data_format = '\001'.join(
                    ['%%%s%%' % i for i in self.fetch_data])
                out = subprocess.check_output(
                    'mpc -f "%s"' % fetch_data_format, shell=True)
                self._updatetime = time.time()
                outlines = out.splitlines()
                if len(outlines) == 3 or len(outlines) == 4:
                    if len(outlines) == 4:
                        recv_data_format, status, _, settings = outlines
                    else:
                        recv_data_format, status, settings = outlines
                    recv_data = recv_data_format.split('\001')
                    for index, key in enumerate(self.fetch_data):
                        self._song[key] = recv_data[index].strip()

                    # [playing] #341/4463   3:48/4:07 (92%)
                    match = re.search(
                        '\[([^\]]+)\] +\#(\d+)/(\d+) +(\d+):(\d+)/(\d+):(\d+)',
                        status)
                    if match:
                        new_playlist_pos = int(match.group(2))
                        if self.playlist_pos != new_playlist_pos:
                            self.playlist_pos = new_playlist_pos
                            events.append(self.EVENT_CHANGE)

                        self.playlist_size = int(match.group(3))
                        self._song['time_elapsed'] = (
                            int(match.group(4))*60 + int(match.group(5)))
                        self._song['length'] = (
                            int(match.group(6))*60 + int(match.group(7)))

                        new_status = match.group(1)
                        if self._player['status'] != new_status:
                            self._player['status'] = new_status
                            if new_status == 'playing':
                                events.append(self.EVENT_PLAY)
                            if new_status == 'paused':
                                events.append(self.EVENT_PAUSE)
                else:
                    if self._player['status'] != 'stopped':
                        self._player['status'] = 'stopped'
                        events.append(self.EVENT_STOP)
                    settings = outlines[-1]
                self._player.update(
                    [i.strip().split(':') for i in settings.split('   ')
                        if i.strip()])
                for event in events:
                    self.call(event)
                if not self._mpd_isalive:
                    self._mpd_isalive = True
                    logger.info("mpd is alive")
                    self.call(self.EVENT_SERVER_WAKEUP)
                subprocess.check_output('mpc idle', shell=True)
            except subprocess.CalledProcessError:
                if self._mpd_isalive:
                    out = subprocess.check_output('ps aux', shell=True)
                    if "/usr/bin/mpd" not in out:
                        self._mpd_isalive = False
                        logger.warn("mpd is down")
                        self.call(self.EVENT_SERVER_DOWN)
                    else:
                        logger.warn("mpc command failed")
                        self.call(self.EVENT_SERVER_HANGUP)
                time.sleep(1)
            except Exception, err:
                logger.critical(traceback.format_exc())
                logger.critical(
                    "unexpect exception in mpd client thread: %s" % str(err))
                time.sleep(1)

    def song(self):
        """Return song data."""
        ret = copy.copy(self._song)
        if self._player['status'] == 'playing':
            ret['time_elapsed'] += int(time.time() - self._updatetime)
        return ret

    def player(self):
        """Return player data."""
        return copy.copy(self._player)


class I2CDisplay(object):

    """Control i2c interface display."""

    def __init__(self, busid, address, left, width, logger=None):
        """Setup display bus/address."""
        self._bus = smbus.SMBus(busid)
        self.address = address
        self.left = left
        self.width = width
        self.height = len(left)
        self.logger = logger if logger else logging
        self._char = {}
        self._old_line = {}
        self._line_scroll_wait = {}
        self._line_scroll_pos = {}
        self._line_scroll_left = {}
        for i in xrange(self.height):
            self._old_line[i] = ''.ljust(self.width)
            self._line_scroll_wait[i] = 0
            self._line_scroll_pos[i] = 0
            self._line_scroll_left[i] = True
        self._power = False
        self._brightness = 0x7F

    def on(self):
        """Turn on display."""
        self._bus.write_byte_data(self.address, 0, 0x0c)
        self.set_brightness(self._brightness)
        self._power = True

    def is_on(self):
        """Return ture if display is on."""
        return self._power

    def off(self):
        """Turn on display."""
        self._bus.write_byte_data(self.address, 0, 0x08)
        self._power = False

    def write(self, string, line=0):
        """Write text."""
        data = map(ord, list(string))
        self.write_raw(data, line)
        self.shift_reset(line)

    def write_raw(self, data, line=0):
        """Write binary to display."""
        if self._old_line[line] == data:
            return
        self._old_line[line] = data
        raw_pos = 0x80 | self.left[line]
        self._bus.write_byte_data(self.address, 0, raw_pos)
        if len(data) > self.width:
            data = data[:self.width]
        self._bus.write_i2c_block_data(self.address, 0x40, data)

    def shift(self, line=0, wait=30):
        """shift text pos."""
        if len(self._old_line[line]) > self.width:
            if self._line_scroll_wait[line] < wait:
                self._line_scroll_wait[line] += 1
                return
            max_pos = len(self._old_line[line]) - self.width
            if self._line_scroll_left[line]:
                if self._line_scroll_pos[line] < max_pos:
                    self._line_scroll_pos[line] += 1
                else:
                    self._line_scroll_left[line] = False
                    self._line_scroll_wait[line] = 0
            else:
                if self._line_scroll_pos[line] > 0:
                    self._line_scroll_pos[line] -= 1
                else:
                    self._line_scroll_left[line] = True
                    self._line_scroll_wait[line] = 0

            raw_pos = 0x80 | self.left[line]
            self._bus.write_byte_data(self.address, 0, raw_pos)
            shift_pos = self._line_scroll_pos[line]
            data = self._old_line[line][shift_pos:self.width+shift_pos]
            self._bus.write_i2c_block_data(self.address, 0x40, data)

    def shift_reset(self, line):
        """Reset text pos."""
        self._line_scroll_left[line] = True
        self._line_scroll_pos[line] = 0
        self._line_scroll_wait[line] = 0

    def set_char(self, pos, data):
        """Set user defined char to CGRAM."""
        raw_pos = 0x40 | pos*8
        data = list(data)
        if raw_pos in self._char and self._char[raw_pos] == data:
            return
        self._char[raw_pos] = data
        self._bus.write_byte_data(self.address, 0, raw_pos)
        self._bus.write_i2c_block_data(self.address, 0x40, list(data))

    def set_brightness(self, brightness):
        """Set display brightness."""
        self._brightness = brightness
        self._bus.write_byte_data(self.address, 0, 0x2a)
        self._bus.write_byte_data(self.address, 0, 0x79)
        self._bus.write_byte_data(self.address, 0, 0x81)
        self._bus.write_byte_data(self.address, 0, brightness)
        self._bus.write_byte_data(self.address, 0, 0x78)
        self._bus.write_byte_data(self.address, 0, 0x28)


def kakasi(string):
    """Convert Kanji/Hiragana/Katakana/Kigou to ascii text.

    # pacman -Sy kakasi
    """
    if not os.path.exists('/usr/bin/kakasi'):
        return string

    p = subprocess.Popen(['/usr/bin/kakasi',
                          '-Ja', '-Ha', '-Ka', '-Ea', '-s', '-i', 'utf8'],
                         stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = p.communicate(string)
    return stdout.strip()

if __name__ == '__main__':
    import atexit
    logging.basicConfig(
        filename='/var/log/mpd-lcd-i2c.log',
        format='[%(levelname)s] %(asctime)s [%(name)s] %(message)s',
        datefmt='%Y/%m/%d %H:%M:%S',
        level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    try:
        app = App(logger=logger)

        @atexit.register
        def whenexit():
            """display of when exit app."""
            logger.info("stop app")
            app.display.off()

        app.main()
    except Exception, err:
        logger.critical("app exit with: %s" % str(err))
        logger.critical(traceback.format_exc())
