# Dependency used: http://pypi.python.org/pypi/icalendar

import threading
import sys,os,getopt
import urllib2
import ConfigParser
import datetime
import time
import signal
import subprocess
import math
from subprocess import Popen, PIPE, STDOUT
from pytz import timezone
import pytz
from icalendar import Calendar, Event, TypesFactory

url = None
ICSFILE = '/tmp/ics-calendar.ics'

class RecorderRecord(object):
    SCHEDULED = 0
    RECORDING = 1
    FINISHED  = 2
    ERROR     = 3
    NOPE      = 4

    begin_dt = None
    end_dt = None
    title = None
    description = None
    location = None
    extention = None
    prefix = None
    dumpdir = None
    command = None
    url = None
    state = SCHEDULED
    pid = None
    pretime_minutes_td = datetime.timedelta(seconds=1 * 60)
    overtime_minutes_td = datetime.timedelta(seconds=1 * 60)

    def __init__(self, title=None, begin=None, end=None):
        self.title = title
        self.begin_dt = begin
        self.end_dt = end 

    def get_state_str(self, state):
        if state == self.SCHEDULED:
            return "Scheduled"
        elif state == self.RECORDING:
            return "Recording"
        elif state == self.FINISHED:
            return "Finished"
        elif state == self.ERROR:
            return "Error"
        elif state == self.NOPE:
            return "Nope"
        else:
            return "Unknown state"

    def change_state(self, new_state):
        if new_state != self.state:
            print "--- State change: " + self.get_state_str(self.state) + " -> " + self.get_state_str(new_state)
        self.state = new_state

    def set_pretime_minutes_td(self, pretime_minutes_td):
        self.pretime_minutes_td = pretime_minutes_td

    def set_overtime_minutes_td(self, overtime_minutes_td):
        self.overtime_minutes_td = overtime_minutes_td

    def set_begin_dt(self, begin):
        self.begin_dt = begin

    def set_end_dt(self, end):
        self.end_dt = end

    def set_title(self, title):
        self.title = title

    def set_location(self, location):
        self.location = location

    def set_duration(self, duration):
        self.end_dt = self.begin_dt + duration

    def set_prefix(self, prefix):
        self.prefix = prefix

    def set_extention(self, ext):
        self.extention = ext

    def set_dumpdir(self, dumpdir):
        self.dumpdir = dumpdir

    def set_command(self, command):
        self.command = command

    def set_url(self, url):
        self.url = url

    def get_filename(self):
        if self.title == None:
            return None

        name = '-'.join([self.title.strip(),
                         str(self.begin_dt)])
        if self.location:
            name = self.location.replace(' ','-') + '-' + name
        if self.extention:
            name = name + '.' + self.extention
        if self.prefix:
            name = self.prefix + name

        name = name.replace(' ','-')
        name = self.dumpdir + '/' + name
        return name

    def get_command(self):
        if self.get_filename() == None or self.url == None:
            return None

        cmd = self.command
        cmd = cmd.replace('$FILE', self.get_filename())
        cmd = cmd.replace('$URL',  self.url)
        return cmd

    def is_showtime(self):
        if (self.begin_dt - self.pretime_minutes_td) < datetime.datetime.now(amsterdam) and (self.end_dt + self.overtime_minutes_td) > datetime.datetime.now(amsterdam):
            return True
        return False

    def show(self):
        print "-     Title %s" % self.title
        print "      Begin %s" % self.begin_dt
        print "        End %s" % self.end_dt
        print "   Location %s" % self.location
        print "     Prefix %s" % self.prefix
        print "  Extention %s" % self.extention
        print "   Filename %s" % self.get_filename()
        print "   Dump Dir %s" % self.dumpdir
        print "    Command %s" % self.get_command()
        print "        URL %s" % self.url

class StreamRecorder(object):
    recorderrecords = []
    refreshing = False
    command = None
    config = None
    rooms = {}
    prefix = None
    extention = None
    dumpdir = "."
    conffile = "stream-vhs.conf"
    schedule_refresh = 60.0
    timer_refresh = 10.0
    pretime_minutes_td = datetime.timedelta(seconds=1 * 60)
    overtime_minutes_td = datetime.timedelta(seconds=1 * 60)
    debug = False
    already_mentioned_no_shows_are_on = 0

    def __init__(self, conffile='stream-vhs.conf', debug=False):
        self.debug = debug
        self.conffile = conffile
        try:
            self.load_configuration()
        except:
            sys.exit(1)

    def load_configuration(self):
        print 'load_configuration %s' % self.conffile
        try:
            if not os.path.exists(self.conffile):
                print "Could not open the configuration file \'%s\'" % self.conffile
                raise
        except:
            raise

        config = ConfigParser.RawConfigParser()

        try:
            config.read(self.conffile)
        except:
            print "Error in configuration file: Syntax error. Please fix the configuration file to be a proper .ini style config file"
            raise

        if not config.has_section('channels'):
            print "Error in configuration file: Expected section 'channels'"
            raise

        if not config.has_option('channels', 'rooms'):
            print "Error in configuration file: Expected option 'rooms' in section 'channels'"
            raise

        # Get the rooms in the channels section, split the string and trim each part
        tmp_rooms = [item.strip() for item in config.get('channels', 'rooms').split(',')]
        for item in tmp_rooms:
            url  = item.split('#')[0].strip()
            try:
                room = item.split('#')[1].strip()
            except:
                print "Syntax error: in 'channels' => 'rooms' it is expected to use: <url> # <room name>, <url> # <room name>..."
                raise
            if not (url and room):
                print "Syntax error: in 'channels' => 'rooms' it is expected to use: <url> # <room name>, <url> # <room name>..."
                raise

            # Combine this in a dict
            self.rooms[room] = url

        if not config.has_section('settings'):
            print "Error in configuration file: Expected section 'settings'"
            raise

        if not config.has_option('settings', 'ical'):
            print "Error in configuration file: Expected option 'ical' in section 'settings'"
            raise
        self.ical_url  = config.get('settings', 'ical').strip()

        if config.has_option('settings', 'prefix'):
            self.prefix    = config.get('settings', 'prefix').strip()

        if config.has_option('settings', 'extention'):
            self.extention = config.get('settings', 'extention').strip()

        if config.has_option('settings', 'dumpdir'):
            self.dumpdir = config.get('settings', 'dumpdir').strip()

        if config.has_option('settings', 'schedule_refresh'):
            self.schedule_refresh = float(config.get('settings', 'schedule_refresh').strip())

        if config.has_option('settings', 'timer_refresh'):
            self.timer_refresh = float(config.get('settings', 'timer_refresh').strip())

        if config.has_option('settings', 'pretime_minutes'):
            try:
                i = int(config.get('settings', 'pretime_minutes').strip())
                self.pretime_minutes_td = datetime.timedelta(seconds=i * 60)
            except:
                print "Error in configuration file: Casting error in the option 'pretime_minutes' in section 'settings'"

        if config.has_option('settings', 'overtime_minutes'):
            try:
                i = int(config.get('settings', 'overtime_minutes').strip())
                self.overtime_minutes_td = datetime.timedelta(seconds=i * 60)
            except:
                print "Error in configuration file: Casting error in the option 'overtime_minutes' in section 'settings'"

        if not config.has_option('settings', 'command'):
            print "Error in configuration file: Expected option 'command' in section 'settings'"
            raise
        self.command = config.get('settings', 'command').strip()

    def download(self):
        if self.ical_url == None:
            print "Error: No iCal URL defined"
            raise

        print "Downloading ical file from \'%s\'" % self.ical_url
        response = urllib2.urlopen(self.ical_url)
        self.ical_raw = response.read()

    def process(self):
        r = None

        cal = Calendar.from_ical(self.ical_raw)

        for component in cal.walk():
            if component.name == 'VEVENT':
                r = RecorderRecord()
                r.set_prefix(self.prefix)
                r.set_extention(self.extention)
                r.set_dumpdir(self.dumpdir)
                r.set_command(self.command)
                r.set_pretime_minutes_td(self.pretime_minutes_td)
                r.set_overtime_minutes_td(self.overtime_minutes_td)

                for item in component.sorted_items():
                    if item[0] == 'DTSTART':
                        r.set_begin_dt(item[1].dt)
                        continue
                    if item[0] == 'DTEND':
                        r.set_end_dt(item[1].dt)
                        continue
                    if item[0] == 'DTSTAMP':
                        continue
                    if item[0] == 'DURATION':
                        r.set_duration(item[1].dt)
                        continue
                    if item[0] == 'LOCATION':
                        r.set_location(item[1])
                        for room, url in self.rooms.items():
                            if room == item[1]:
                                r.set_url(url)
                                break
                        continue
                    if item[0] == 'SUMMARY':
                        r.set_title(item[1])
                        continue
                # Throw on the stack
                self.recorderrecords.append(r)


    def process_exists(self, search_pid):
        ps = subprocess.Popen("ps ax", shell=True, stdout=subprocess.PIPE)
        ps_pid = ps.pid
        output = ps.stdout.read()
        ps.stdout.close()
        ps.wait()

        for line in output.split("\n"):
            if line != "" and line != None:
                fields = line.split()
                pid = fields[0]

                if(pid == str(search_pid)):
                    return True
        return False


    def exec_subprocess(self, r):
        if r.state != RecorderRecord().SCHEDULED:
            print "Error: state is not scheduled for the recording:"
            r.show()

        if self.debug:
            cmd = 'sleep 20'.split()
        else:
            cmd = r.get_command().split()

        p = subprocess.Popen(cmd, stdout=PIPE, stdin=PIPE, stderr=STDOUT)
        r.pid = p.pid

    def start_recording(self, r):
        if r.state == RecorderRecord().NOPE or r.state == RecorderRecord().ERROR:
            return

        if r.state == RecorderRecord().SCHEDULED:
            self.exec_subprocess(r)

            r.change_state(RecorderRecord().RECORDING)
            r.show()

        if r.state == RecorderRecord().RECORDING:
            r.change_state(RecorderRecord().RECORDING)

            # Check if the PID is still alive
            if not self.process_exists(r.pid):
                r.change_state(RecorderRecord().FINISHED)
                r.show()
            return

        if  r.state == RecorderRecord().FINISHED:
            r.change_state(RecorderRecord().FINISHED)
            return

    def stop_recording(self, r):
        if r.state == RecorderRecord().RECORDING:
            if r.pid != None:
                try:
                    os.kill(r.pid, signal.SIGTERM)
                    time.sleep(1)
                    os.kill(r.pid, signal.SIGKILL)
                    r.change_state(RecorderRecord().FINISHED)
                    r.show()
                except:
                    print "Warning: Process already shot"

    def whatson(self):
        something = False
        for r in self.recorderrecords:
            # NOPE
            if r.get_command() == None or r.get_command() == '':
                r.state = RecorderRecord().NOPE
                continue
            if r.state == RecorderRecord().NOPE:
                continue

            # Is the show on yet?
            if r.is_showtime():
                something = True
                self.already_mentioned_no_shows_are_on = 0
                self.start_recording(r)
            else:
                self.stop_recording(r)

        if something == False and self.already_mentioned_no_shows_are_on == 0:
            print "No shows are on at the moment"
            self.already_mentioned_no_shows_are_on = 1
        elif something == False and self.already_mentioned_no_shows_are_on > 0:
            go_back = 0.005 / math.pow(self.already_mentioned_no_shows_are_on, 2)
            go_fwd  = 0.05 / math.pow(self.already_mentioned_no_shows_are_on, 2)

            for i in xrange(0, self.already_mentioned_no_shows_are_on):
                sys.stdout.write('\b')
                sys.stdout.flush()
                time.sleep(go_back)
            for i in xrange(0, self.already_mentioned_no_shows_are_on):
                sys.stdout.write('.')
                sys.stdout.flush()
                time.sleep(go_fwd)
            self.already_mentioned_no_shows_are_on += 1

    def timer(self):
        # Timer loop
        self.whatson()
        threading.Timer(self.timer_refresh, self.timer).start()

    def refresh(self):
        self.refreshing = True
        recorderrecords = []
        self.download()
        self.load_configuration()
        self.process()

        print "Ready"

        # Check
#        for r in self.recorderrecords:
#            r.show()

        self.refreshing = False
#        threading.Timer(self.schedule_refresh, self.refresh).start()

    def go(self):
        self.refresh()
        self.timer()

def usage():
    print '<program> -h|--help -c|--conf <config file>'


#def printit():
#    threading.Timer(5.0, printit).start()
#    print "Hello, World!"


########### MAIN ############
if __name__ == "__main__":
    conf = 'stream-vhs.conf'
    dryrun = False

    amsterdam = timezone('Europe/Amsterdam')
    try:
        opts, args = getopt.getopt(sys.argv[1:], "dhc:", ["dryrun", "help", "conf="])
    except getopt.GetoptError:
        print str(err)
        usage()
        sys.exit(1)

    for o, a in opts:
        if o in ("-d", "--dryrun"):
            dryrun = False
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-c", "--conf"):
            conf = a
        else:
            assert False, "unhandled option"

    print "Stream VHS"
    s = StreamRecorder(conf, dryrun)
    s.go()

