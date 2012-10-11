# -*- coding: utf-8 -*-
#:vim:et:ts=4:sts=4:sw=4:
import rrdtool
import os
import os.path
import sys
import glob
import hashlib
import tempfile
import time
import syslog
import sqlite3
import traceback
import datetime
import struct
import binascii
from colorsys import hls_to_rgb

import config

def sensor_rrd_path(s):
    return '%s/sensor_%s.rrd' % (config.DATA_PATH, s)

# returns (path, sensor_name) tuples
def all_sensors():
    return [(r, os.path.basename(r[:-4])) 
        for r in glob.glob('%s/*.rrd' % config.DATA_PATH)]

def create_rrd(sensor_id):
    # start date of 10 seconds into 1970 is used so that we can
    # update with prior values straight away.
    if 'voltage' in sensor_id:
        args = [ 
                '--step', '3600',
                'DS:temp:GAUGE:7200:1:10',
                'RRA:AVERAGE:0.5:1:87600']
    elif 'fridge_on' in sensor_id:
        args = [
                '--step', '300',
                'DS:temp:GAUGE:600:-100:500',
                'RRA:LAST:0.5:1:1051200']
    else:
        args = [
                '--step', '300',
                'DS:temp:GAUGE:600:-100:500',
                'RRA:AVERAGE:0.5:1:1051200']

    rrdtool.create(sensor_rrd_path(sensor_id), 
                '--start', 'now-60d',
                *args)

# stolen from viewmtn, stolen from monotone-viz
def colour_from_string(str):
    def f(off):
        return ord(hashval[off]) / 256.0
    hashval = hashlib.sha1(str).digest()
    hue = f(5)
    li = f(1) * 0.15 + 0.55
    sat = f(2) * 0.5 + .5
    return ''.join(["%.2x" % int(x * 256) for x in hls_to_rgb(hue, li, sat)])

def graph_png(start, length):
    os.environ['MATT_PNG_BODGE_COMPRESS'] = '4'
    os.environ['MATT_PNG_BODGE_FILTER'] = 'paeth'
    rrds = all_sensors()

    graph_args = []
    have_volts = False
    for n, (rrdfile, sensor) in enumerate(rrds):
        unit = None
        if 'avrtemp' in sensor:
            continue
        if 'voltage' in sensor:
            have_volts = True
            vname = 'scalevolts'
            graph_args.append('DEF:%(vname)s=%(rrdfile)s:temp:AVERAGE:step=3600' % locals())
            unit = 'V'
        elif 'fridge_on' in sensor:
            vname = 'fridge_on'
            graph_args.append('DEF:raw%(vname)s=%(rrdfile)s:temp:LAST' % locals())
            graph_args.append('CDEF:%(vname)s=raw%(vname)s,3,+' % locals())
        else:
            vname = 'temp%d' % n
            graph_args.append('DEF:raw%(vname)s=%(rrdfile)s:temp:AVERAGE' % locals())
            # limit max temp to 50
            graph_args.append('CDEF:%(vname)s=raw%(vname)s,35,GT,UNKN,raw%(vname)s,0.1,*,2,+,IF' % locals())
            unit = '<span face="Liberation Serif">º</span>C'

        format_last_value = None
        if unit:
            try:
                last_value = float(rrdtool.info(rrdfile)['ds[temp].last_ds'])
                format_last_value = ('%f' % last_value).rstrip('0.') + unit
            except ValueError:
                pass
        width = config.LINE_WIDTH
        legend = config.SENSOR_NAMES.get(sensor, sensor)
        colour = config.SENSOR_COLOURS.get(legend, colour_from_string(sensor))
        if format_last_value:
            print_legend = '%s (%s)' % (legend, format_last_value)
        else:
            print_legend = legend
        graph_args.append('LINE%(width)f:%(vname)s#%(colour)s:%(print_legend)s' % locals())

    end = int(start+length)
    start = int(start)

    tempf = tempfile.NamedTemporaryFile()
    dateformat = '%H:%M:%S %Y-%m-%d'
    watermark = ("Now %s\t"
                "Start %s\t"
                "End %s" % (
                datetime.datetime.now().strftime(dateformat),
                datetime.datetime.fromtimestamp(start).strftime(dateformat),
                datetime.datetime.fromtimestamp(end).strftime(dateformat) ))

    args = [tempf.name, '-s', str(start),
        '-e', str(end),
        '-w', str(config.GRAPH_WIDTH),
        '-h', str(config.GRAPH_HEIGHT),
        '--slope-mode',
        '--border', '0',
#        '--vertical-label', 'Voltage',
        '--y-grid', '0.1:1',
        '--dynamic-labels',
        '--grid-dash', '1:0',
        '--zoom', str(config.ZOOM),
        '--color', 'GRID#00000000',
        '--color', 'MGRID#aaaaaa',
        '--color', 'BACK#ffffff',
        '--disable-rrdtool-tag',
        '--pango-markup',
        '--watermark', watermark,
        '--imgformat', 'PNG'] \
        + graph_args
    args += ['--font', 'DEFAULT:12:%s' % config.GRAPH_FONT]
    args += ['--font', 'WATERMARK:10:%s' % config.GRAPH_FONT]
    if have_volts:
        args += ['--right-axis', '10:-20', # matches the scalevolts CDEF above
            '--right-axis-format', '%.0lf',
#            '--right-axis-label', 'Temperature'
            ]

	print>>sys.stderr, ' '.join("'%s'" % s for s in args)
    rrdtool.graph(*args)
    #return tempf
    return tempf.read()

def validate_values(measurements):
    for m in measurements:
        if m == 85:
            yield 'U'
        else:
            yield '%f' % m

def sensor_update(sensor_id, measurements, first_real_time, time_step):
    try:
        open(sensor_rrd_path(sensor_id))
    except IOError, e:
        create_rrd(sensor_id)

    if measurements:
        values = ['%d:%s' % p for p in 
            zip((first_real_time + time_step*t for t in xrange(len(measurements))),
                validate_values(measurements))]

        rrdfile = sensor_rrd_path(sensor_id)
        # XXX what to do here when it fails...
        for v in values:
            try:
                rrdtool.update(rrdfile, v)
            except rrdtool.error, e:
                print>>sys.stderr, "Bad rrdtool update '%s': %s" % (v, str(e))
                traceback.print_exc(file=sys.stderr)

        # be paranoid
        #f = file(rrdfile)
        #os.fsync(f.fileno())

def debug_file(mode='r'):
    return open('%s/debug.log' % config.DATA_PATH, mode)

def record_debug(lines):
    f = debug_file('a+')
    f.write('===== %s =====\n' % time.strftime('%a, %d %b %Y %H:%M:%S'))
    f.writelines(('%s\n' % s for s in lines))
    f.flush()
    return f


def tail_debug_log():
    f = debug_file()
    f.seek(0, 2)
    size = f.tell()
    f.seek(max(0, size-30000))
    return '\n'.join(l.strip() for l in f.readlines()[-400:])

def convert_ds18b20_12bit(reading):
    value = struct.unpack('>h', binascii.unhexlify(reading))[0]
    return value * 0.0625

def time_rem(name, entries):
    val_ticks = int(entries[name])
    val_rem = int(entries['%s_rem' % name])
    tick_wake = int(entries['tick_wake']) + 1
    tick_secs = int(entries['tick_secs'])
    return val_ticks + float(val_rem) * tick_secs / tick_wake

def parse(lines):

    start_time = time.time()
   
    debugf = record_debug(lines)

    entries = dict(l.split('=', 1) for l in lines)
    if len(entries) != len(lines):
        raise Exception("Keys are not unique")

    num_sensors = int(entries['sensors'])
    num_measurements = int(entries['measurements'])

    sensors = [entries['sensor_id%d' % n] for n in xrange(num_sensors)]

    meas = []
    for s in sensors:
        meas.append([])

    for n in xrange(num_measurements):
        vals = [convert_ds18b20_12bit(x) for x in entries["meas%d" % n].strip().split()]
        if len(vals) != num_sensors:
            raise Exception("Wrong number of sensors for measurement %d" % n)
        # we make an array of values for each sensor
        for s in xrange(num_sensors):
            meas[s].append(vals[s])

    avr_now = time_rem('now', entries)
    avr_first_time = time_rem('first_time', entries)
    avr_comms_time = time_rem('comms_time', entries)
    time_step = float(entries['time_step'])

    debugf.write('now %f, comms_time %f, first_time %f, delta %f\n' %
            (avr_now, avr_comms_time, avr_first_time, avr_now - avr_comms_time))

    if 'avrtemp' in entries:
        avrtemp = val_scale(int(entries['avrtemp']))
        sensor_update('avrtemp', [avrtemp], time.time(), 1)

    if 'voltage' in entries:
        voltage = 0.001 * int(entries['voltage'])
        sensor_update('voltage', [voltage], time.time(), 1)

    if 'fridge_status' in entries:
        fridge_on = int(entries['fridge_status'])
        sensor_update('fridge_on', [fridge_on], time.time(), 1)

    if 'fridge' in entries:
        fridge_setpoint = float(entries['fridge'])
        sensor_update('fridge_setpoint', [fridge_setpoint], time.time(), 1)
    #sqlite 
    # - time
    # - voltage
    # - boot time

    first_real_time = time.time() - (avr_now - avr_first_time)

    for sensor_id, measurements in zip(sensors, meas):
        # XXX sqlite add
        sensor_update(sensor_id, measurements, first_real_time, time_step)

    timedelta = time.time() - start_time
    debugf.write("Updated %d sensors in %.2f secs\n" % (len(sensors), timedelta))
    debugf.flush()
