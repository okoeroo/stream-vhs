# Dependency used: http://pypi.python.org/pypi/icalendar

import threading
import sys,os,getopt
import urllib2
import ConfigParser
from icalendar import Calendar, Event, TypesFactory

url = None
ICSFILE = '/tmp/ics-calendar.ics'


class RecorderRecord(object):
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

    def __init__(self, title=None, begin=None, end=None):
        self.title = title
        self.begin_dt = begin
        self.end_dt = end 

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
        return name.replace(' ','-')

    def get_command(self):
        if self.get_filename() == None or self.url == None:
            return None

        cmd = self.command
        cmd = cmd.replace('$FILE', self.get_filename())
        cmd = cmd.replace('$URL',  self.url)
        return cmd

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
    command = None
    config = None
    rooms = {}
    prefix = None
    extention = None
    dumpdir = "."

    def __init__(self, conffile='/tmp/stream-vhs.conf'):
        try:
            self.load_configuration(conffile)
        except:
            sys.exit(1)

    def load_configuration(self, conffile):
        print 'load_configurationi %s' % conffile
        try:
            if not os.path.exists(conffile):
                print "Could not open the configuration file \'%s\'" % conffile
                raise
        except:
            raise

        print 'load_configuration'
        config = ConfigParser.RawConfigParser()

        try:
            config.read(conffile)
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
            self.extention = config.get('settings', 'dumpdir').strip()

        if not config.has_option('settings', 'command'):
            print "Error in configuration file: Expected option 'command' in section 'settings'"
            raise
        self.command = config.get('settings', 'command').strip()
        print self.command

        print "Ready"

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

        # Check
        for r in self.recorderrecords:
            r.show()


    def refresh(self):
        self.download()
        self.process()


def usage():
    print '<program> -h|--help -c|--conf <config file>'


def printit():
    threading.Timer(5.0, printit).start()
    print "Hello, World!"


########### MAIN ############
if __name__ == "__main__":
    conf = 'stream-vhs.conf'

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hc:", ["help", "conf="])
    except getopt.GetoptError as err:
        print str(err)
#        usage()
        sys.exit(1)

    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-c", "--conf"):
            conf = a
        else:
            assert False, "unhandled option"

#    printit()

    print "Stream VHS"
    s = StreamRecorder(conf)
    s.refresh()

