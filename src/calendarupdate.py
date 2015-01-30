#!/usr/bin/python

import mechanize
import time
import os.path
import servertools
import csv
import icalendar
import logging
import datetime
import pytz
import yaml
import socket

yamlfile = 'navidile_settings.yml'
settings = yaml.load(file(yamlfile))
hostname = socket.gethostname()

def main():
    linkurl=settings['zone_cal']['url']

    servertools.init_logger1('calendarexport');
    zonecsvfile=os.path.join(settings[hostname]['zone_stuff_loc'], 'zonecal.csv')
    if 'check_zone' in settings[hostname] and settings[hostname]['check_zone']:
        getZoneCal(linkurl, zonecsvfile);
    else:
        try:
            import urllib
            urllib.urlretrieve('ftp://navidile.mine.nu:2932/test/zonecal.csv', filename=zonecsvfile)
        except IOError:
            zonecsvfile=os.path.join(settings[hostname]['zone_stuff_loc'], 'zonecal-backup.csv')
            LOGGER = logging.getLogger('navidile'); 
            LOGGER.warn('IOException:',  exc_info=1);  
            
    try:
        parse(zonecsvfile);
    except IOError:
        LOGGER = logging.getLogger('navidile4');
        LOGGER.warn('IOException:',  exc_info=1);        

def converttime(date1, time1):
    return datetime.datetime(*time.strptime(date1+ " "+ time1, "%m/%d/%Y %I:%M %p")[0:6], tzinfo=pytz.timezone("US/Eastern"))

def removeNonAscii(s): return "".join(filter(lambda x: ord(x)<128, s))

def parse(zonecsvfile):
    cal = icalendar.Calendar()
    cal.add('prodid', '-//Zone Calendar//zone.medschool.pitt.edu//EN')
    cal.add('version', '2.0')
    cal.add('X-WR-CALNAME', 'Zone Calendar')
    cal.add('X-WR-CALDESC', 'PITTMED Zone Calendar')
    cal.add('X-WR-TIMEZONE', 'America/New_York')

    f = open(zonecsvfile, 'rb');
    calreader = csv.DictReader(f)

    for row in calreader:
        if row['All day event']=='False':
            #print row  
            try:
                event = icalendar.Event()
                event.add('summary', row['Subject'])
                description = row['Description']
                description = removeNonAscii(description)
                description = description.replace(u"Zone:  ", u"")
                
                event.add('Description', description)
                event.add('dtstart', converttime(row['Start Date'], row['Start Time']))
                event.add('dtend', converttime(row['End Date'], row['End Time']))
                event.add('location', row['Location'])
    #            event.add('dtstamp', datetime.datetime.now())
                #event['uid'] = '20050115T101010/27346262376@mxm.dk'
                event.add('priority', 1)
    
                cal.add_component(event)
            except UnicodeDecodeError:
                LOGGER = logging.getLogger('navidile');
                LOGGER.warn('IOException {0}'.format(row),  exc_info=1);
                

    icsfile =os.path.join(settings[hostname]['cal_location'], 'zonecal.ics')
    f = open(icsfile, 'w')
    f.write(cal.as_string().replace('\\n', '').replace('\r', '').replace(';VALUE=DATE', ''))
    f.close()
    servertools.upload_file(settings, icsfile, 'zonecal.ics')


def getZoneCal(linkurl, destfile):
    cyear='2014'
    try:
        br = mechanize.Browser()
        import keyring
        username = settings['calendar_check'][cyear]['username']
        password = keyring.get_password(settings['calendar_check'][cyear]['site'], username)
        br.add_password('zone.medschool.pitt.edu', username, password.encode('ascii'))

        br.set_handle_robots(False)
        br.open(linkurl)
        br.select_form(nr = 0)
        now = datetime.datetime.now();
        thismonth_start = now.replace(day=1);
        future = now+datetime.timedelta(4*30);
        br.find_control("cblDatasources$0").items[0].selected=False
        br.find_control("cblDatasources$2").items[0].selected=True
        br.find_control("cblDatasources$3").items[0].selected=True
        #br["cblDatasources$0"]="unchecked"
        #br["cblDatasources$2"]="checked"
        #br["cblDatasources$3"]="checked"
        br["txtFromDate"] = thismonth_start.strftime('%m/%d/%Y');
        br["txtToDate"]= future.strftime('%m/%d/%Y');
        
        #page = response1.read();
        #print page
        req = br.click(nr=0)
        response2 = br.open(req)

        
        page=response2.read()
        #page = urllib.urlopen(mainurl).read();
        #print page
        
        f = open(destfile, 'w');
        f.write(page);
        f.close();       
    except IOError:
        LOGGER = logging.getLogger('calendarexport');
        LOGGER.warn('IOException',  exc_info=1);



if __name__ == "__main__":
    main();


