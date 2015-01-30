#!/usr/bin/python

# todo:
# wiki?
#list of docs?


# external libraries
import yaml
import feedparser
from BeautifulSoup import BeautifulSoup
import mechanize
import icalendar
import pytz
from sqlalchemy import *

from sqlalchemy.ext.declarative import declarative_base
#from sqlalchemy.orm import relation, sessionmaker
from sqlalchemy.orm import sessionmaker

# internal libraries


import ms_maker

# default libraries
import imaplib
import urllib
import re
import time
import datetime
import os.path
import socket
import json
import urllib2
import sched
import email
import sys
import logging

import nav4api
from email.mime.text import MIMEText


hostname = socket.gethostname()


def update_settings():
    # update settings from yaml file
    global settings

    yamlfile = 'navidile_settings.yml'
    path = os.path.dirname(os.path.abspath(__file__))
    yamlfile = os.path.join(path, yamlfile)
    settings = yaml.load(file(yamlfile))

    tempdir = os.path.join(os.getenv('HOME'), 'navidile_testing')
    if not os.path.exists(tempdir):
        os.makedirs(tempdir)
    if hostname not in settings:
        settings[hostname] = dict()
    if 'log_loc' not in settings[hostname]:
        settings[hostname]['log_loc'] = tempdir
    if 'db_engine' not in settings[hostname]:
        settings[hostname]['db_engine'] = 'sqlite:///{0}/test.db'.format(tempdir)
    if 'htmlloc' not in settings[hostname]:
        settings[hostname]['htmlloc'] = tempdir
    if 'ms_sched_location' not in settings[hostname]:
        settings[hostname]['ms_sched_location'] = tempdir
    if 'cal_location' not in settings[hostname]:
        settings[hostname]['cal_location'] = tempdir
    if 'host_loc' not in settings[hostname]:
        settings[hostname]['host_loc'] = "http://127.0.0.1"

    yaml.dump(file(yamlfile))


# setup database stuff
Base = declarative_base()

yamlfile = 'navidile.yml'
update_settings()
import servertools


if 'db_engine' in settings[hostname]:
    db_engine = settings[hostname]['db_engine']
else:
    raise Exception("I don't know where to to go for the database!")


# start the scheduler
schedule = sched.scheduler(time.time, time.sleep)


# set up the logger
def init_logger(logger_name, filename=None):
    if not filename:
        filename = os.path.join(settings[hostname]['log_loc'], logger_name + '.log')
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    ch = logging.FileHandler(filename)
    sh = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    # add formatter 
    ch.setFormatter(formatter)
    #    sh.setFormatter(formatter)
    # add ch to logger
    if len(logger.handlers) == 0:
        logger.addHandler(ch)
        logger.addHandler(sh)
    return logger


def main(_):
    # start the logger
    global logger
    logger = init_logger('navidile4')
    logger.info('Navidile started')

    global settings
    update_settings()

    #run these on startup every time

    for i in range(1, 1000):
        tasks = s.query(NavidileTask).all()
        for task in tasks:
            if not task.last_ran or (task.last_ran + datetime.timedelta(
                    seconds=task.run_interval)) < datetime.datetime.now() or task.force_run:
                if task.name == "update_webpages":
                    update_webpages(task)
                elif task.name == "update_calendars":
                    update_calendars(task)
                elif task.name == "update_subscribers":
                    update_subscribers(task)
                elif task.name == "update_navidile_players":
                    update_navidile_players(task)
                elif task.name == "update_mediasite_sched":
                    update_mediasite_sched(task)
                elif task.name == "update_course_docs":
                    update_course_docs(task)
                elif task.name == "update_course_db":
                    update_course_db(task)
                elif task.name == "update_recordings":
                    update_recordings(task)
                elif task.name == "redundancy_check":
                    redundancy_check(task)
                elif task.name == "update_everything":
                    update_calendars(task)
                    update_subscribers(task)
                    # update_subscriptions(task)
                    update_navidile_players(task)
                    update_mediasite_sched(task)
                    update_course_docs(task)
                    update_course_db(task)
                    update_recordings(task)
                    redundancy_check(task)
                task.last_ran = datetime.datetime.now()
                if task.force_run:
                    task.force_run = False

        s.commit()

        time.sleep(15)


# prevent some weird error reading rss feeds
def remove_non_ascii(line):
    output = ''.join([x for x in line if ord(x) < 128])
    return output.replace(u'\u2013', '-').replace(u'\u2019', '').replace(u'\u2014', '')


def update_calendar(ms_class):
    logger.info('Updating  Calendar for {0}:'.format(ms_class.cyear))
    # retrieve relevant calendar items from database
    cal_items = s.query(CalendarItem).filter(CalendarItem.cyear == ms_class.cyear).all()
    cal_string = ("\n"
                  "BEGIN:VCALENDAR\n"
                  "VERSION:2.0\n"
                  "PRODID:-//Navigator Calendar//navigator.medschool.pitt.edu//EN\n"
                  "X-WR-CALDESC:PITTMED Calendar\n"
                  "X-WR-CALNAME:PITTMED Calendar\n"
                  "X-WR-TIMEZONE:America/New_York\n"
                  "BEGIN:VEVENT\n"
                  "SUMMARY:Calendar may not be ready yet! See http://students.medschool.pitt.edu/wiki/index.php/Calendars\n"
                  "DTSTART:20120608T200000\n"
                  "DTEND:20200723T195900\n"
                  "UID:000@zone.medschool.pitt.edu\n"
                  "LOCATION:http://students.medschool.pitt.edu/wiki/index.php/Calendars\n"
                  "PRIORITY:5\n"
                  "END:VEVENT\n"
                  "END:VCALENDAR\n"
                  "\n"
                )

    if len(cal_items) > 0:
        # make an icalendar and add initial values
        cal = icalendar.Calendar()
        cal.add('prodid', '-//Navigator Calendar//navigator.medschool.pitt.edu//')
        cal.add('version', '2.0')
        cal.add('X-WR-CALNAME', 'PITTMED%s' % ms_class.cyear)
        cal.add('X-WR-CALDESC', 'PITTMED%s Navigator Calendar' % ms_class.cyear)
        cal.add('X-WR-TIMEZONE', 'America/New_York')

        # is there a template already?  If so, just start with that instead...
        if ms_class.google_calendar_template:
            try:
                editable_version = ms_class.google_calendar_template
                file_handle = urllib.urlopen(editable_version)
                data = file_handle.read()

                cal = icalendar.Calendar.from_ical(data)
                cal.set('prodid', '-//Navigator Calendar//navigator.medschool.pitt.edu//')
                cal.set('version', '2.0')
                cal.set('X-WR-CALNAME', 'PITTMED%s Navigator' % ms_class.cyear)
                cal.set('X-WR-CALDESC', 'PITTMED%s Navigator Calendar' % ms_class.cyear)
                cal.set('X-WR-TIMEZONE', 'America/New_York')

            except IOError:
                logger.warn('IOerror', exc_info=1)
            except ValueError:
                logger.warn('ValueError', exc_info=1)

        # make a calendar for each event in the calendar
        for cal_item in cal_items:
            event = icalendar.Event()
            # set up all the ical fields
            event.add('SUMMARY', cal_item.name)
            event.add('DTSTART', dt_to_utc(cal_item.start_date))
            event.add('DTEND', dt_to_utc(cal_item.end_date))
            event.add('UID', cal_item.idno + "@navigator.medschool.pitt.edu")
            # event.add('LOCATION', cal_item.location)
            event.add('priority', 5)
            cal.add_component(event)
        cal_string = cal.to_ical().replace(';VALUE=DATE', '').replace('-TIME', '')

    file_name = os.path.join(settings[hostname]['cal_location'], str(ms_class.cyear) + '_navi.ics')
    if not os.path.exists(settings[hostname]['cal_location']):
        os.makedirs(settings[hostname]['cal_location'])
    f = open(file_name, 'wb')
    f.write(cal_string)
    f.close()
    #servertools.upload_file(settings, fileloc, fname )
    f = open(file_name.replace('.ics', '.txt'), 'wb')
    f.write(cal_string)
    f.close()
    logger.info('Done Updating  Calendar for {0}:'.format(ms_class.cyear));


# look for possible database redundancies
def redundancy_check(task):
    # find orphaned recordings and add them to existing courses
    for recording in s.query(Recording).filter(Recording.course_uid == None).all():
        course = s.query(Course).filter(Course.course_id == recording.course_id).first()
        if course:
            recording.course_uid = course.unique_id
            s.add(recording)
    s.commit()

    # check for recordings that didn't appear to have recorded
    for ms_class in s.query(MSClass).all():
        ursr = s.query(ScheduledRecording).filter(ScheduledRecording.recorded == False,
                                                  ScheduledRecording.excluded == False,
                                                  ScheduledRecording.end_date < (
                                                      datetime.datetime.now() - datetime.timedelta(minutes=60)),
                                                  ScheduledRecording.end_date > (
                                                      datetime.datetime.now() - datetime.timedelta(days=3)),
                                                  ScheduledRecording.cyear == ms_class.cyear,
                                                  ScheduledRecording.notified_unrecorded == False).all()
        if ursr:
            warning_txt = ('Hi, the following lecture(s) did not appear to  record:',)
            for u in ursr:
                warning_txt += (u.l0name,)
                u.notified_unrecorded = True

                s.commit()
            warning_txt += "Please ignore if they weren't supposed to be recorded! Or maybe they went into the wrong course???  Fix in phpmyadmin!",
            warning = NavidileWarning('Missing recording?', '\n'.join(warning_txt), ms_class.cyear)
            s.add(warning)
            s.commit()

        #look for expected recordings that haven't been scheduled
        ussr = s.query(ScheduledRecording).filter(ScheduledRecording.scheduled == False,
                                                  ScheduledRecording.excluded == False,
                                                  ScheduledRecording.start_date < (
                                                      datetime.datetime.now() - datetime.timedelta(days=4)),
                                                  ScheduledRecording.start_date > datetime.datetime.now(),
                                                  ScheduledRecording.cyear == ms_class.cyear,
                                                  ScheduledRecording.notified_unscheduled == False).all()

        if ussr:
            warning_txt = ('Hi, the following lecture(s) have not been scheduled:',)
            for u in ussr:
                warning_txt += u.l0name,
                u.notified_unscheduled = True
                s.commit()
            warning_txt += "Please ignore if they aren't supposed to be recorded!",
            warning = NavidileWarning('Missing podcast?', '\n'.join(warning_txt), ms_class.cyear, tonotify=False)
            s.add(warning)
            s.commit()

        #look for mediasite that don't have podcasts
        np = s.query(Recording).filter(Recording.podcast_url == "",
                                       Recording.notified_no_podcast == False,
                                       Recording.cyear == ms_class.cyear,
                                       Recording.date_added < (
                                           datetime.datetime.now() - datetime.timedelta(minutes=7 * 60))).all()

        if np:
            warning_txt = ("I couldn't find the podcast for the following lecture(s)",)
            for u in np:
                warning_txt += u.name,
                s.commit()
                u.notified_no_podcast = True
            warning_txt += "Have you checked if the rss feed is set to more than 10 items?  Is the podcast server still running?",
            warning = NavidileWarning('Missing podcast?', '\n'.join(warning_txt), ms_class.cyear)
            s.add(warning)
            s.commit()


#export zone calendar events to an ical
def update_zone_calendar():
    logger.info('Updating Zone Calendar:')
    try:
        rss_url = settings['global']['zone_cal_rss']
        feed = feedparser.parse(rss_url)

        #parse through items
        for item in feed["items"]:

            #get fields in the calendar
            name = remove_non_ascii(item.title)
            idno = item.link[-4:].strip('=')
            description = remove_non_ascii(item.description)

            soup = BeautifulSoup(description)
            tags = soup.findAll('div')
            start_time_str = ""
            end_time_str = ""
            location = ""
            for tag in tags:

                if 'Start Time:' in tag.text:
                    start_time_str = tag.text.replace('Start Time:', '')
                elif 'End Time:' in tag.text:
                    end_time_str = tag.text.replace('End Time:', '')
                elif 'Location:' in tag.text and 'Description:' not in tag.text:
                    location = remove_non_ascii(tag.text).replace('Location:', "")
                    #print location

            zci = s.query(ZoneCalItem).get(idno)
            if not zci:
                zci = ZoneCalItem(idno, name, start_time_str, end_time_str, location, description)

            s.add(zci)
        s.commit()

        icsfile = os.path.join(settings[hostname]['cal_location'], 'zone.ics')

        cal = icalendar.Calendar()
        cal.add('prodid', '-//Zone Calendar//zone.medschool.pitt.edu//EN')
        cal.add('version', '2.0')
        cal.add('X-WR-CALDESC', 'PITTMED Zone Calendar')
        cal.set('X-WR-CALNAME', 'PITTMED Zone Cal')
        cal.add('X-WR-TIMEZONE', 'America/New_York')

        zonecalitems = s.query(ZoneCalItem).all();

        if len(zonecalitems) == 0:
            logger.info('no ZONECAL items to add!')
            return
        else:
            logger.info('Found {0} zonecal items'.format(len(zonecalitems)))

        for zci in zonecalitems:

            if zci.end_date - zci.start_date > datetime.timedelta(hours=6):
                zci.end_date = zci.start_date + datetime.timedelta(hours=6)
                zci.name = zci.name + " (truncated)";
            event = icalendar.Event()
            event.add('SUMMARY', zci.name)
            event.add('LOCATION', zci.location)

            event.add('DTSTART', dt_to_utc(zci.start_date))
            event.add('DTEND', dt_to_utc(zci.end_date))
            #event.add('dtstamp', cal_item['stamp_date'])
            event.add('UID', "%s%s" % (zci.idno, "@zone.medschool.pitt.edu"))
            event.add('PRIORITY', 5)
            cal.add_component(event)

        f = open(icsfile, 'wb')
        f.write(cal.to_ical())
        f.close()


    except IOError:

        logger.warn('IOException:', exc_info=1);


        #try to steal mediasite_url info from navigator (doesn't really work)


def update_mediasite_urls(course):
    if course.navigator_url == None:
        return
    br = mechanize.Browser()
    br.set_handle_robots(False)
    try:

        br.open(course.navigator_url)
        response = br.response()
        response.set_data(response.get_data().replace("<br/>", "<br />"))
        br.set_response(response)
        forms = mechanize.ParseResponse(response, backwards_compat=False)
        form = forms[0]
        username = settings['navigator']['username']
        password = settings['navigator']['password']

        form['ctl00$bodyContent$txtUserName'] = username
        form['ctl00$bodyContent$txtPassword'] = password
        #br.submit()
        request2 = form.click()
        response2 = mechanize.urlopen(request2)

        page = response2.read()

        #page = urllib2.urlopen(page_url).read()
        soup = BeautifulSoup(page)
        for incident in soup('a', alt='Lecture Recording Catalog'):
            if not course.mediasite_url:
                course.mediasite_url = incident['href']
                logger.info('Added mediasite url for {0}: {1}'.format(course.name, incident['href']));
        for incident in soup('a', title='Podcast RSS'):
            if not course.podcast_url:
                course.podcast_url = incident['href']
                logger.info('Added podcast url for {0}: {1}'.format(course.name, incident['href']));
    except IOError, e:
        logger.warn('Couldn''t access this url...: {0} {1}'.format(course.name, course.navigator_url), exc_info=0);
        'Couldn''t access this url...: {0} {1}'.format(course.name, course.navigator_url)

        course.last_error = str(e)
    except Exception, e:
        logger.warn('HTTPError:{0}'.format(course.name), exc_info=0);
        course.last_error = str(e)


# process alert subscriptions
def subscribe_message(mailto, cyear, subs):
    alerts = get_subscribed_alerts(subs)
    email_text = "You are currently subscribed to Navidile email alert: %s.  Reply to this message to unsubscribe to this alert." % alerts
    mailfrom = 'alerts' + cyear + '-' + subs + '@students.medschool.pitt.edu'
    msg = MIMEText(email_text)
    msg['Subject'] = "Navidile Subscription: %s" % alerts
    msg['From'] = mailfrom
    msg['Reply-To'] = mailfrom.replace('students.medschool.pitt.edu', 'navidile.mine.nu')
    msg['To'] = mailto
    servertools.send_out(mailfrom, [mailto], msg, settings)


def unsubscribe_message(mailto, cyear, subs):
    alerts = get_subscribed_alerts(subs)
    email_text = "You have unsubscribed to these Navidile email alert: %s.  Reply to this message to resubscribe to this alert at any time." % alerts
    mailfrom = 'alerts' + cyear + '+' + subs + '@students.medschool.pitt.edu'
    msg = MIMEText(email_text)
    msg['Subject'] = "Navidile Subscription: %s" % alerts
    msg['From'] = mailfrom
    msg['To'] = mailto
    msg['Reply-To'] = mailfrom.replace('students.medschool.pitt.edu', 'navidile.mine.nu')
    servertools.send_out(mailfrom, [mailto], msg, settings)


def get_subscribed_alerts(subs):
    output = []
    if 'g' in subs:
        output.append('Posted Exams')
    if 'c' in subs:
        output.append('Course Docs')
    if 'r' in subs:
        output.append('Lecture recordings')
    if 'b' in subs:
        output.append('Course Blogs')
    return ', '.join(output)


def update_course_db(task):
    opener = nav4api.build_opener(settings=settings)
    current_year = datetime.datetime.now().year
    for year in range(current_year - 1, current_year + 2):
        ncourses = nav4api.courses_by_academic_year(year, opener)
        for ncourse in ncourses:
            ncourse['displayName'] = ncourse['displayName'].strip()
            cyears = ncourse['curriculumYears']
            if len(cyears) == 1 and ncourse['displayName'] and ncourse['startDate'] and not ncourse['isPlaceholder']:
                cyear = cyears[0]
                course = s.query(Course).get(ncourse['displayName'])
                if not course:
                    course = Course(ncourse['displayName'], cyear, course_id=ncourse['moduleID'], auto_number=False,
                                    keep_updated=False)
                if not course.course_id and not course.navigator_url:
                    course.course_id = ncourse['moduleID']
                    course.navigator_url = "http://navigator.medschool.pitt.edu/CourseOverview.aspx?moduleID={0}".format(
                        course.course_id)
                if not course.rec_exclude:
                    course.rec_exclude = '["Small Group", "Exam", "PBL", "Independent"]'
                if ncourse['startDate']:
                    course.start_date = datetime.datetime.strptime(ncourse['startDate'], '%Y-%m-%dT%H:%M:%S.%f00')
                if ncourse['endDate']:
                    course.end_date = datetime.datetime.strptime(ncourse['endDate'], '%Y-%m-%dT%H:%M:%S.%f00')
                    #disable autoadding of courses:
                if len(s.query(Course).filter(Course.cyear == course.cyear,
                                              Course.course_id == course.course_id).all()) == 0:
                    #s.add(course)
                    #s.commit()
                    pass

    """
            if ncourse['displayName'] and ncourse['startDate'] and  datetime.datetime.strptime(ncourse['startDate'], '%Y-%m-%dT%H:%M:%S.%f00') >datetime.datetime.now():
                course = s.query(Course).get(ncourse['displayName'])
                if not course:
                    course = Course(ncourse['displayName'],  "UNK", course_id=ncourse['moduleID'] , auto_number=False, keep_updated=False)
                course.course_id=ncourse['moduleID']
                if ncourse['startDate']:
                    course.start_date =datetime.datetime.strptime(ncourse['startDate'], '%Y-%m-%dT%H:%M:%S.%f00') 
                if ncourse['endDate']:
                    course.end_date = datetime.datetime.strptime(ncourse['endDate'], '%Y-%m-%dT%H:%M:%S.%f00') 
    
                
                if course.cyear == "UNK":
                    m1 = re.match('\\((\\d+)\\)',course.name)
                    if m1:
                        name_only= m1.group(1)
                        academic_year = int(m1.group(2))
                        
                        prev_year_course = s.query(Course).filter(Course.name == " {0} ({1})".format(name_only, academic_year-1))
                        if prev_year_course:
                            course.cyear = prev_year_course.cyear+1
                            s.add(course)
                        later_year_course = s.query(Course).filter(Course.name == " {0} ({1})".format(name_only, academic_year+1))
                        if later_year_course:
                            course.cyear = prev_year_course.cyear-1
     
                        s.add(course)
            """
    s.commit()


# update courses
def update_course_docs(task):
    for course in s.query(Course).filter(Course.navigator_url != None).all():
        if not course.course_id or course.course_id == 0:
            idno = course.navigator_url.replace('&toolType=course', '').split('=')[-1]
            course.course_id = int(idno)
        if not course.course_id == 0 and 'viewModule' in course.navigator_url:
            course.navigator_url = "http://navigator.medschool.pitt.edu/courseOverview.aspx?moduleID=" + str(
                course.course_id)

        if not course.mediasite_url or not course.podcast_url:
            update_mediasite_urls(course)
            s.commit()
        if not course.mediasite_id and course.mediasite_url:
            course.mediasite_id = course.mediasite_url.split("=")[-1]
        if course.mediasite_id and not course.mediasite_url:
            course.mediasite_url = "http://mediasite.medschool.pitt.edu/som_mediasite/Catalog/pages/rss.aspx?catalogId=" + course.mediasite_id

        if 'ALL COURSES' not in course.name and (not task.selected_only or course.keep_updated):
            check_for_doc_updates_nav4(course)


def update_mediasite_sched(task):
    for msclass in s.query(MSClass).all():

        items = []
        for course in s.query(Course).filter(Course.cyear == msclass.cyear).all():
            if course.do_reset:
                pass;
                course.do_reset = False
                s.query(CalendarItem).filter(CalendarItem.mediasite_fldr == course.mediasite_fldr).delete()
                s.query(ScheduledRecording).filter(ScheduledRecording.mediasite_fldr == course.mediasite_fldr).delete()
                s.commit()
            if course.navigator_url and (not task.selected_only or course.keep_updated):
                theseitems = check_for_cal_updates_nav4(course)
                for item in theseitems:
                    items.append(item)
                    #logger.info('{0} calendar event(s) for {1}...'.format(len(items), course.name))
        generate_mediasite_schedule_class(items, msclass);


def update_recordings(task):
    logger.info('checking mediasite for new recordings...')
    for course in s.query(Course).filter(Course.mediasite_url != None).all():
        count = len(
            s.query(Recording).filter(Recording.course_name == course.name, Recording.cyear == course.cyear).all())
        if 'ALL COURSES' not in course.name and (course.keep_updated or count == 0):
            check_for_new_recordings(course)


def update_navidile_players(task):
    task.last_report = "";
    logger.info('updating navidile players...')
    courses = s.query(Course).filter(Course.podcast_url != None).all()

    for course in courses:
        count = len(
            s.query(Recording).filter(Recording.course_uid == course.unique_id, Recording.navidile_url != "").all())
        if not task.selected_only or (task.selected_only and course.keep_updated or count == 0):
            task.last_report += ('\n doing course: {0}'.format(course.name))
            update_navidile_player(course, task)


def update_webpages(task):
    logger.info('updating pages...')
    for msclass in s.query(MSClass).all():
        construct_html_pagevids_all(msclass)


def update_calendars(task):
    for msclass in s.query(MSClass).all():
        update_calendar(msclass)
    update_zone_calendar()


def update_subscriptions(reschedule=True):
    logger.info('updating subscriptions...')
    if not all(k in settings[hostname] for k in ('email_in_username', 'email_in_server', 'email_in_password')):
        logging.warn('not checking requests!')
        return
    username = settings[hostname]['email_in_username']
    imaphost = settings[hostname]['email_in_server']
    password = settings[hostname]['email_in_password']
    try:

        server = imaplib.IMAP4_SSL(imaphost)
        server.login(username, password)

        # get all unprocessed messages
        server.select("INBOX.Navidile")
        items = server.search(None, "UNSEEN")[1]
        items = items[0].split()

        # fetch messages and send them to the script
        itemnum = len(items)

        logger.info('found {0} msgs'.format(itemnum))
        for i in items:
            data = server.fetch(i, "(RFC822)")[1]
            text = data[0][1].replace('\r', '')
            email_msg = email.message_from_string(text)
            processed = process_request(email_msg['From'], [email_msg['To']], email_msg)
            #subscriber_request_queue.put()
            #server.store(md, '+FLAGS', '\\Deleted')

    except:
        logger.error('Error', exc_info=1)


def process_request(mailfrom, rcpttos, email_msg):
    processed = False
    try:

        Base.metadata.create_all(engine)

        Session = sessionmaker(bind=engine)
        s = Session()
        #while not subscriber_request_queue.empty():
        #   item=subscriber_request_queue.get()

        mailto1 = rcpttos[0]
        mailto = mailto1.split('@')[0]

        logger.info("mailto {0} ".format(mailto))
        txt = mailto

        re1 = '(alerts)'  # Word 1
        re2 = '(\d{4})'  # Integer Number 1
        re3 = '([\\+\\-])'  # Any Single Character 1
        re4 = '(\w+)'  # Any Single Character 2

        rg = re.compile(re1 + re2 + re3 + re4, re.IGNORECASE | re.DOTALL)
        m = rg.match(txt)
        if 'forceupdate' in mailto1:
            update_mediasite_sched(reschedule=False)
            outmailfrom = 'navidile@students.medschool.pitt.edu'
            msg = MIMEText(
                "okay, I updated the schedules... Go look here: http://students.medschool.pitt.edu/cal -Navidile")
            msg['Subject'] = "Navidile Force Update"
            msg['From'] = 'navidile@students.medschool.pitt.edu'
            msg['Reply-To'] = outmailfrom.replace('students.medschool.pitt.edu', 'navidile.mine.nu')
            msg['To'] = mailfrom
            servertools.send_out(outmailfrom, [mailfrom], msg, settings)
            #return
            processed = True

        if m:
            #word1=m.group(1)
            cyear = m.group(2)
            c1 = m.group(3)
            subs = m.group(4)

            logger.info("request {0} {1} {2}".format(mailfrom, cyear, subs))
            if c1 == '+':
                sub1 = s.query(Subscriber).get(mailfrom)
                if not sub1:
                    sub1 = Subscriber(mailfrom, cyear, subs)
                else:
                    sub1.subscriptions += subs;
                s.add(sub1)
                s.commit()
                subscribe_message(mailfrom, cyear, subs)
            if c1 == '-':
                sub1 = s.query(Subscriber).get(mailfrom)
                if not sub1:
                    sub1 = Subscriber(mailfrom, cyear, subs)
                else:
                    for s in subs:
                        sub1.subscriptions = sub1.subscriptions.replace(s, '')
                s.add(sub1)
                s.commit()
                unsubscribe_message(mailfrom, cyear, subs)
            processed = True
        if mailfrom == 'ntkurapati@gmail.com' and mailto == 'stopnavidile':
            sys.exit()

        subject = email_msg['Subject']
        if 'Invitation to a Mediasite presentation: ' in subject:
            logger.info("confirmed scheduling of  {0} ".format(subject))
            subject = subject.replace('Invitation to a Mediasite presentation: ', '')
            recording = s.query(ScheduledRecording).filter(ScheduledRecording.lname == subject).first()
            if not recording:
                recording = s.query(ScheduledRecording).filter(ScheduledRecording.l0name == subject).first()
            if recording:
                recording.scheduled = True
                s.commit()

            processed = True



            #dbntools.storemsg(item.mailfrom, item.rcpttos[0], item.data, cyear, dblocation)
            #subscriber_request_queue.task_done()
    except TypeError:
        logger.warn('TypeError', exc_info=1)
    return processed


def update_subscribers(task):
    subscribers = s.query(Subscriber).all()
    for subscriber in subscribers:
        update_subscriber(subscriber, task)


def update_navidile_player(course, task):
    feed = feedparser.parse(course.podcast_url)
    for item in feed["items"]:
        mp3_url = item['link']
        #idno = mp3_url.split('/')[-1].replace('.mp3', '').replace('-', '');
        idno = mp3_url.split('/')[-2]
        rec = s.query(Recording).get((idno, course.unique_id))
        if rec:
            rec.podcast_url = mp3_url
            rec.navidile_url = "{0}/{1}/{2}/{3}.html".format(settings[hostname]['host_loc'], course.cyear, course.name,
                                                             rec.idno)

            s.commit()
            #else:
            #task.last_report+=(removeNonAscii('Podcast but no video for {0} in course {1}'.format(item["title"], course.name)))
    navidile_link = settings[hostname]['host_loc'].replace('navidile_player', '{0}-all-lr.html'.format(course.cyear))
    last_rec_url = navidile_link
    next_rec_url = settings[hostname]['host_loc'].replace('navidile_player', '{0}-all-lr.html'.format(course.cyear))
    last_rec = None
    for rec in s.query(Recording).filter(Recording.course_uid == course.unique_id).order_by(Recording.rec_date).all():
        if rec.next_id:
            next_rec = s.query(Recording).get((rec.next_id, course.unique_id))
            if next_rec and next_rec.navidile_url:
                next_rec_url = next_rec.navidile_url
        else:
            next_rec_url = navidile_link
        make_navidile_player(course, rec, last_rec_url, next_rec_url, task)
        last_rec_url = rec.navidile_url
        if last_rec:
            if not last_rec.next_id or last_rec.next_id != rec.idno:
                last_rec.next_id = rec.idno
                last_rec.force_recreate = True
                s.add(last_rec)
        last_rec = rec
        s.commit()


def get_directory(filename):
    path = os.path.dirname(os.path.abspath(__file__))
    fileAndPath = os.path.join(path, filename)
    return fileAndPath


def make_navidile_player(course, rec, last_rec_url, next_rec_url, task):
    #mp3_url, idno, course ,title

    if not rec.podcast_url or rec.podcast_url == "":
        return

    filedir = os.path.join(settings[hostname]['htmlloc'], 'navidile_player', str(course.cyear), course.name)
    if not os.path.exists(filedir):
        os.makedirs(filedir)
    filename = os.path.join(filedir, rec.idno + '.html')
    if os.path.exists(filename) and not rec.force_recreate and not task.force_run:
        return
    if rec.force_recreate:
        rec.force_recreate = False
    scripturl = 'http://mediasite.medschool.pitt.edu/som_mediasite/FileServer/Presentation/{0}/manifest.js'.format(
        rec.idno)
    refs = []
    slidebaseurl = ''

    try:

        imagerefs = re.findall(r'CreateSlide\("",(\d+),', urllib2.urlopen(scripturl).read())
        for i in imagerefs:
            refs.append(int(i))

        sr = re.findall(r'SlideBaseUrl="(.+?)";', urllib2.urlopen(scripturl).read())
        for i in sr:
            slidebaseurl = i
            break
    except urllib2.HTTPError:
        logger.warn('auth request')
    except IOError, urllib2.HTTPError:
        logger.warn('IOError', exc_info=1)
    path = os.path.dirname(os.path.abspath(__file__))
    playerTemplate = 'player_template.html'
    playerTemplate = os.path.join(path, playerTemplate)
    f = open(playerTemplate)
    data = f.read()
    f.close()
    data = data.replace('%SLIDEBASEURL%', slidebaseurl).replace('%MP3URL%', rec.podcast_url).replace('%REFS%',
                                                                                                     repr(refs));
    data = data.replace('%RECDATE%', rec.rec_date.isoformat())
    data = data.replace('%MAINDIR%', settings[hostname]['host_loc'])
    data = data.replace('%TITLE%', rec.name)
    data = data.replace('%COURSETITLE%', rec.course_name)
    data = data.replace('%LASTPRESENTATION%', last_rec_url)
    data = data.replace('%NEXTPRESENTATION%', next_rec_url)
    if rec.presenters:
        data = data.replace('%PRESENTERS%', rec.presenters)
    else:
        data = data.replace('%PRESENTERS%', "Unknown")
    data = data.replace('%MEDIASITEPLAYERLINK%', rec.mediasite_url)
    f = open(unicode(filename), 'w');
    f.write(remove_non_ascii(data))
    f.close();
    #servertools.upload_file(settings, filename,'navidile_player/'+str(course.cyear)+'/'+idno+'.html')


def update_subscriber(subscriber, task):
    if 'r' in subscriber.subscriptions:
        mailfrom = 'alerts%s-r@navidile.mine.nu' % subscriber.cyear
        for course in s.query(Course).filter(Course.keep_updated == True).all():
            updatedrecs = s.query(Recording).filter(Recording.date_added > subscriber.last_update).filter(
                Recording.course_name == course.name).filter(Recording.cyear == subscriber.cyear).all()
            if course.keep_updated and len(updatedrecs) > 0:
                messagelines = []
                construct_vids_message(messagelines, updatedrecs, subscriber)
                send_out_update("\n".join(messagelines), mailfrom, subscriber,
                                '[Navidile] %s: Recordings Added' % ( course.name))
    if 'c' in subscriber.subscriptions:
        mailfrom = 'alerts%s-c@navidile.mine.nu' % subscriber.cyear
        for course in s.query(Course).all():

            updateddocs = s.query(Document).filter(Document.date_added > subscriber.last_update).filter(
                Document.course_name == course.name).filter(Document.cyear == subscriber.cyear).all()
            if course.keep_updated and len(updateddocs) > 0:
                messagelines = []
                construct_docs_message(messagelines, updateddocs, subscriber)
                send_out_update("\n".join(messagelines), mailfrom, subscriber,
                                '[Navidile] %s: Documents Added' % ( course.name))
    if 'w' in subscriber.subscriptions:
        mailfrom = 'alerts%s-w@navidile.mine.nu' % subscriber.cyear
        for warning in s.query(NavidileWarning).filter(NavidileWarning.cyear == subscriber.cyear,
                                                       NavidileWarning.date_added > subscriber.last_update).all():
            send_out_update(warning.warning, mailfrom, subscriber, '[Navidile]: %s' % ( warning.subject))
    subscriber.last_update = datetime.datetime.now()
    s.add(subscriber)
    s.commit()


def send_out_update(output, mail_from, subscriber, header):
    email_text = output
    msg = MIMEText(remove_non_ascii(email_text))
    msg['Subject'] = header
    msg['From'] = mail_from
    msg['To'] = subscriber.email_addr
    servertools.send_out('alerts@students.medschool.pitt.edu', [subscriber.email_addr], msg, settings)


def parse_date(date_str):
    date_str = date_str.replace(' 0:00 am', ' 12:00 pm')
    return datetime.datetime.strptime(date_str, '%m.%d.%Y %I:%M %p')


def dt_to_utc(naivedate):
    eastern = pytz.timezone('US/Eastern')
    loc_dt = eastern.localize(naivedate)
    utc = pytz.utc
    return loc_dt.astimezone(utc)


def check_for_new_recordings(course):
    feed = feedparser.parse(course.mediasite_url)
    course.rec_count = len(feed['items'])

    if course.rec_count == 0:
        newurl = "http://mediasite.medschool.pitt.edu/som_mediasite/Catalog/pages/rss.aspx?catalogId={0}".format(
            course.mediasite_id)
        feed = feedparser.parse(newurl)

    #rec_name_list=[]

    for item in feed["items"]:

        #rec_name_list.append(item["title"])
        print item["title"]
        # get unique id no of video
        idno = item['link'].split('/')[-1]
        idno1 = remove_non_ascii(idno)
        print idno
        #check if already in database
        rec = s.query(Recording).get((idno1, course.unique_id))

        if not rec:
            rec = Recording(idno1, name=remove_non_ascii(item["title"]), mediasite_url=item["link"], course=course,
                            pub_date="")
        rec.rec_date = datetime.datetime.fromtimestamp(time.mktime(item.published_parsed))
        #print item.published_parsed


        sr = s.query(ScheduledRecording).filter(ScheduledRecording.l0name == rec.name,
                                                ScheduledRecording.course_name == course.name).first()
        if not sr:
            sr = s.query(ScheduledRecording).filter(ScheduledRecording.lname == rec.name,
                                                    ScheduledRecording.course_name == course.name).first()
        if not sr:
            sr = s.query(ScheduledRecording).filter(ScheduledRecording.lname == rec.name).first()
        folder = None
        if sr:
            sr.recorded = True
            rec.presenters = sr.presenters
            s.add(sr)
            folder = s.query(Folder).get(sr.folderID)
        if not folder:
            folder = s.query(Folder).filter(Folder.startDate == rec.rec_date).filter(
                Folder.course == course.name).filter(Folder.cyear == rec.cyear).first()
        if folder:
            rec.folder_id = folder.folderID

        s.add(rec)

    s.commit()


def check_for_doc_updates_nav4(course):
    foldername = "None"
    try:

        opener = nav4api.build_opener(settings=settings)

        course_folders = nav4api.course_folders(course.course_id, opener)
        for folder in course_folders:
            folder_obj = s.query(Folder).get(folder['folderID'])
            if not folder_obj:
                folder_obj = Folder(folder, course)
            s.add(folder_obj)
            s.commit()

            foldername = folder['displayName']
            if 'virtualHomeFolder' != folder['displayName']:

                for page in nav4api.folder_pages(course.course_id, folder['folderID'], opener):

                    try:
                        for document in nav4api.page_docs(course.course_id, folder['folderID'], page['pageID'], opener):
                            doc_obj = s.query(Document).get(document['url'])

                            if not doc_obj:
                                doc_obj = Document(folder, page, document, course)
                            s.add(doc_obj)
                            s.commit()
                    except KeyError:
                        pass

    except urllib2.HTTPError:
        logger.warn('HTTPError in doc update course {0}, folder{1}:'.format(course.name, foldername), exc_info=1);


        #get all the calendar events + recordings, and add them to calendar


def check_for_cal_updates_nav4(course):
    foldername = "none"
    opener = nav4api.build_opener(settings=settings)
    calitems = [];
    i = 1
    prev_recording_event = None
    try:
        course_folders = nav4api.course_folders(course.course_id, opener)
        if len(course_folders) == 0:
            logger.warn('No folders for : {0}'.format(course.name));
        for folder in course_folders:
            #print folder['displayName']
            if folder['displayName'] is None:
                folder['displayName'] = 'Noname'
            foldername = folder['displayName']
            if 'virtualHomeFolder' not in folder['displayName']:
                if len(course_folders) == 0:
                    logger.warn('No pages for : {0}, {1}'.format(course.name, folder['folderID']));
                for page in nav4api.folder_pages(course.course_id, folder['folderID'], opener):


                    name = page['displayName'].strip()
                    start_time = page['startTime']
                    end_time = page['endTime']
                    id1 = page['pageID']

                    if start_time and end_time:

                        ## First add/update the google calendar item
                        ci = s.query(CalendarItem).get(id1)
                        if not ci:
                            ci = CalendarItem(id1, name, start_time, end_time, course)

                        ci.lec_id = i;
                        ci.course_name = course.name
                        ci.cyear = course.cyear
                        ci.auto_number = course.auto_number
                        ci.course_uid = course.unique_id
                        ci.mediasite_fldr = course.mediasite_fldr

                        ci.presenters = remove_non_ascii(
                            re.sub('<[^>]*>', '', page['source']).replace('and ', '; ').replace('   ', ';').replace(
                                '\n', ' '))


                        #datetime.datetime.strptime('2012-05-17T00:00:00.0000000', '%Y-%m-%dT%H:%M:%S.%f00')

                        ci.start_date = datetime.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S.%f00')
                        ci.end_date = datetime.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S.%f00')

                        #fix in case start date is after end date
                        if ci.end_date < ci.start_date:
                            ci.start_date -= datetime.timedelta(minutes=720)

                        if not ci.presenters:
                            ci.presenters = "Mediasite Presenter"
                            ## HOW TO FIX THIS???
                        try:
                            excludes = json.loads(course.rec_exclude)
                        except ValueError:
                            logger.warn("Can't parse the excludes: {0}".format(course.rec_exclude), exc_info=1)
                            excludes = ['l234242lkjl2jro2'];

                        if not excludes:
                            excludes = ['l234242lkjl2jro2'];
                        exclude = False
                        for text in excludes:
                            if text in ci.name:
                                exclude = True
                                break;
                        ci.to_record = not exclude

                        s.add(ci)
                        try:
                            s.commit()
                        except sqlalchemy.exc.IntegrityError:
                            pass

                            ## Then add a recording for the mediasite xml
                        recording_event = s.query(ScheduledRecording).get(id1)
                        if not recording_event:
                            recording_event = ScheduledRecording(ci)
                            recording_event.folderID = folder['folderID']
                        if not recording_event.course_uid:
                            recording_event.course_uid = course.unique_id

                        if not exclude and not recording_event.combined_with_another:
                            #try:
                            #    logger.info('Excluding by request: {0}'.format(recording_event.lname,).encode('utf-8'))
                            #except UnicodeEncodeError:
                            #    pass


                            # first check if there was a previous item (if not already combine)
                            if not prev_recording_event:
                                prev_recording_event = recording_event
                                calitems.append(recording_event)
                                i = i + 1
                            # otherwise, check if this one overlaps with the last one
                            elif abs(recording_event.start_date - prev_recording_event.start_date) < datetime.timedelta(
                                    seconds=60):
                                try:
                                    logger.info('Combining: {0} {1} {2} {3}'.format(recording_event.lname,
                                                                                    prev_recording_event.lname,
                                                                                    recording_event.start_date,
                                                                                    prev_recording_event.start_date))
                                except UnicodeEncodeError:
                                    pass
                                prev_recording_event.combine_as_same(recording_event)
                            #if it doesn't overlap, just add as a separate item
                            else:
                                prev_recording_event = recording_event
                                calitems.append(recording_event)
                                i = i + 1
                        else:
                            recording_event.excluded = True

                        s.add(recording_event)
                        s.commit()
    except urllib2.HTTPError:
        logger.warn('HTTPError in cal update course {0}, folder{1}:'.format(course.name, foldername), exc_info=1);
    return calitems


def generate_mediasite_schedule_class(cal_items1, msclass):
    cal_items = sorted(cal_items1, key=lambda item: item.start_date)
    new_sched = []
    if len(cal_items) > 0:

        new_sched = [cal_items.pop(0)]
        while len(cal_items) > 0:
            last = new_sched[-1]
            a = cal_items.pop(0)
            overlap = last.compare_overlap(a)

            if overlap < datetime.timedelta(seconds=0):
                overlap *= -1
            # combine but don't add if comes right after another
            if overlap < datetime.timedelta(minutes=16) and last.mediasite_fldr == a.mediasite_fldr:

                #don't combine if done already!
                if not a.combined_with_another and last.excluded == a.excluded:
                    last.combine(a)
            elif not a.combined_with_another and overlap < datetime.timedelta(
                    minutes=2) and last.mediasite_fldr != a.mediasite_fldr:
                last.cut_short = True
                new_sched.append(a)
            else:
                new_sched.append(a)
            s.add(a)
            s.commit()
            #for a in new_sched:

    if not os.path.exists(settings[hostname]['ms_sched_location']):
        os.makedirs(settings[hostname]['ms_sched_location'])

    new_sched = s.query(ScheduledRecording).filter(ScheduledRecording.cyear == msclass.cyear) \
        .filter(ScheduledRecording.excluded == 0) \
        .filter(ScheduledRecording.combined_with_another == 0) \
        .filter(ScheduledRecording.start_date > datetime.datetime.now()) \
        .filter(ScheduledRecording.start_date < datetime.datetime.now() + datetime.timedelta(days=7)) \
        .order_by(ScheduledRecording.start_date) \
        .all()

    filename = "%s_combined.xml" % (msclass.cyear)
    filepath = os.path.join(settings[hostname]['ms_sched_location'], filename)

    ms_maker.make_xml(new_sched, filepath, recordername=msclass.recorder_name)
    #servertools.upload_file(settings,filepath, "sched/"+filename )       

    filename = "%s_all_future.xml" % (msclass.cyear)
    filepath = os.path.join(settings[hostname]['ms_sched_location'], filename)

    new_sched2 = s.query(ScheduledRecording).filter(ScheduledRecording.cyear == msclass.cyear).filter(
        ScheduledRecording.excluded == 0).filter(ScheduledRecording.combined_with_another == 0).filter(
        ScheduledRecording.start_date > datetime.datetime.now()).order_by(ScheduledRecording.start_date).all()

    ms_maker.make_xml(new_sched2, filepath)


def construct_docs_message(messagelines, updateddocs, subscriber):
    messagelines.append(
        "Navidile found these documents updated on Navigator.  Make sure you are logged in to Navigator <http://navigator.medschool.pitt.edu> to access them. \n")
    lastfolder = ""
    for doc in updateddocs:
        if lastfolder != doc.folder_name:
            messagelines.append('\n')
            messagelines.append("==%s==" % ( remove_non_ascii(doc.folder_name)))
            lastfolder = doc.folder_name
        messagelines.append(
            "-{0} [{1}] <{2}> at {3}".format(remove_non_ascii(doc.doc_name), remove_non_ascii(doc.doc_ext),
                                             doc.full_url,
                                             doc.date_added))
    messagelines.append(
        "\nTo unsubscribe to this alert, reply to this email with 'unsubscribe' in the message. Your last update was at {0}.".format(
            subscriber.last_update))


def construct_vids_message(messagelines, updatedrecordings, subscriber):
    messagelines.append("The following lecture(s) were just posted:\n")
    for rec in updatedrecordings:
        messagelines.append("-{0} [{1}] <{2}> at {3}".format(rec.name, 'vid', rec.mediasite_url, rec.date_added))
    messagelines.append(
        "\nTo unsubscribe to this alert, reply to this email with 'unsubscribe' in the message.  Your last update was at {0}.".format(
            subscriber.last_update))


def construct_html_pagevids_all(msclass):
    #LOGGER = logging.getLogger('navidile')
    lines = []
    lines.append('<head><META NAME="robots" CONTENT="noindex,nofollow"><title>Navidile {0}</title></head>\n'.format(
        msclass.cyear))
    lines.append('<body>\n')
    lines.append('<link href="navidile_stylesheet.css" rel="stylesheet"  type="text/css" />\n')
    if msclass.notice:
        lines.append('<p>%s</p>' % msclass.notice)
    for course in s.query(Course).filter(Course.cyear == msclass.cyear).filter(
                    Course.start_date < datetime.datetime.now()).order_by(desc(Course.start_date)).all():

        lines.append('<h3>%s<br>%s</h3>\n' % (course.name, get_info_line(course) ))

        lines.append('<table>\n')
        recs2 = s.query(Recording).filter(Recording.course_uid == course.unique_id).order_by(
            desc(Recording.rec_date)).all()
        for rec in recs2:
            if not rec.navidile_url:
                lines.append('<tr><td>{3}</td><td>{2}</td><td><a href="{0}" rel="nofollow">{1}</a></td></tr>\n'.format(
                    rec.mediasite_url, rec.name.replace(';', '<br>'), rec.rec_date.strftime("%Y-%m-%d"),
                    rec.rec_date.strftime("%A")[0:3]))
            else:

                lines.append(
                    '<tr><td>{5}</td><td>{4}</td><td><a href="{0}" rel="nofollow">{1}</a> </td><td>[<a href = "{2}">mp3</a>]</td><td>[<a href = "{3}">navidile</a>]</td></tr>\n'.format(
                        rec.mediasite_url, rec.name.replace(';', '<br>+'), rec.podcast_url, rec.navidile_url,
                        rec.rec_date.strftime("%Y-%m-%d"), rec.rec_date.strftime("%A")[0:3]))



        #lines.append('</ul>')
        lines.append('</table><hr />\n')
    lines.append('<p>Last updated: %s</p>\n' % datetime.datetime.now().strftime('%c'))
    #    lines.append('<p style="font-family:verdana;font-size:10px">To subscribe to email alerts when recordings are posted, send an email to <a href="mailto:navidile+r@macrowiz49b.mine.nu">navidile+r@macrowiz49b.mine.nu</a>.</p>')
    lines.append('</body>')
    fullhtml = ''.join(lines)
    htmlloc = os.path.join(settings[hostname]['htmlloc'], '%s-all-lr.html' % msclass.cyear)

    try:
        file1 = open(htmlloc, 'w')
        file1.write(fullhtml)
        file1.close()
    except:
        logger.warn('error', exc_info=1)
        #servertools.upload_file(settings,htmlloc,'%s-all-lr.html' % cyear)


def get_info_line(course):
    string = []

    if course.mediasite_url:
        string.append('[<a href=%s>%s</a>]' % (course.mediasite_url.replace('rss.aspx', 'catalog.aspx'), 'mediasite'))
    if course.podcast_url:
        string.append('[<a href=%s>%s</a>]' % (course.podcast_url, 'podcast'))
        string.append('[<a href=%s>%s</a>]' % (course.podcast_url.replace('http', "itpc"), 'iTunes'))
    if course.navigator_url:
        string.append('[<a href=%s>%s</a>]' % (course.navigator_url, 'navigator'))
    return ''.join(string)


engine = create_engine(db_engine)
Base = declarative_base(bind=engine)


class Folder(Base):
    __tablename__ = 'folder_nav4'

    folderID = Column(String(225), primary_key=True)
    startDate = Column(Date, nullable=True)
    displayName = Column(String(225), nullable=False)
    sequence_no = Column(Integer, nullable=False)
    course = Column(String(225), nullable=False)
    cyear = Column(Integer, nullable=False)


    def __init__(self, folder, course):
        #orig_name.parts=  orig_name.split(' ',1)[0]

        #XXX: Dates/academic year will now come from the API
        self.date = None

        self.folderID = folder['folderID']
        self.startDate = folder['officialStartDate']
        if folder['displayName'] is None:
            self.displayName = 'NoName'
        else:
            self.displayName = folder['displayName']
        self.sequence_no = folder['sequence']
        self.course = course.name
        self.cyear = course.cyear


class Course(Base):
    __tablename__ = 'courses'

    unique_id = Column(String(25), primary_key=True)
    name = Column(String(225))
    cyear = Column(String(5), nullable=False)
    course_id = Column(Integer, nullable=True)
    mediasite_id = Column(String(225))
    mediasite_fldr = Column(String(225))
    navigator_url = Column(String(225))
    mediasite_url = Column(String(225))
    podcast_url = Column(String(225))
    rec_exclude = Column(String(225))
    auto_number = Column(Boolean)
    keep_updated = Column(Boolean)
    last_updated = Column(DateTime, nullable=False)

    start_date = Column(Date)
    end_date = Column(Date)

    do_reset = Column(Boolean, nullable=False)

    mediasite_url_auto = Column(String(225))
    podcast_url_auto = Column(String(225))
    last_error = Column(String(225))


    def __init__(self, name, cyear, course_id=None, navigator_url=None, mediasite_url=None, podcast_url=None,
                 rec_exclude=None, auto_number=False, keep_updated=False):
        self.name = name
        self.cyear = cyear
        self.mediasite_fldr = name
        self.navigator_url = navigator_url
        self.mediasite_url = mediasite_url
        self.podcast_url = podcast_url
        self.rec_exclude = rec_exclude
        self.keep_updated = keep_updated
        self.last_updated = datetime.datetime.now()
        self.auto_number = auto_number
        #self.last_recording=None
        self.start_date = None
        self.end_date = None
        self.course_id = course_id
        self.unique_id = '-'.join((str(cyear), str(course_id)))

        self.do_reset = False


class Document(Base):
    __tablename__ = 'docs_nav4'
    url = Column(String(400), primary_key=True)
    full_url = Column(String(400), nullable=False)
    doc_name = Column(String(225), nullable=False)
    folder_name = Column(String(225), nullable=False)
    course_name = Column(String(225), nullable=False)
    cyear = Column(Integer, nullable=False)
    folder_no = Column(String(225), nullable=False)
    doc_ext = Column(String(5), nullable=False)

    date_added = Column(DateTime, nullable=False)
    last_updated = Column(DateTime, nullable=False)


    def __init__(self, folder, page, document, course):
        self.url = document['url']
        self.doc_name = remove_non_ascii(document['title'])
        self.full_url = "http://navigator.medschool.pitt.edu" + self.url
        if folder['displayName'] is None:
            self.folder_name = 'NoName'
        else:
            self.folder_name = remove_non_ascii(folder['displayName'])
        self.folder_no = folder['folderID']
        self.course_name = course.name
        self.cyear = course.cyear

        self.doc_ext = ""

        self.last_updated = datetime.datetime.now()
        self.date_added = datetime.datetime.now()


    def __repr__(self):
        return "%s %s %s" % (self.folder_name, self.idno, self.doc_name)


class NavidileWarning(Base):
    __tablename__ = 'warnings'

    subject = Column(String(225), nullable=False)
    date_added = Column(DateTime, nullable=False, primary_key=True)
    last_updated = Column(DateTime, nullable=False)
    warning = Column(String(800), nullable=False)
    cyear = Column(Integer, nullable=False)
    tonotify = Column(Boolean, nullable=False)


    def __init__(self, subject, warningtxt, cyear, tonotify=True):
        self.subject = remove_non_ascii(subject)
        self.warning = remove_non_ascii(warningtxt)
        self.cyear = cyear

        self.last_updated = datetime.datetime.now()
        self.date_added = datetime.datetime.now()
        self.tonotify = tonotify


    def __repr__(self):
        return "%s %s %s" % (self.folder_name, self.idno, self.doc_name)


class Recording(Base):
    __tablename__ = 'recordings'
    idno = Column(String(225), primary_key=True)
    name = Column(String(500), nullable=False)
    rec_date = Column(DateTime, nullable=True)
    course_id = Column(Integer, nullable=True)
    course_uid = Column(String(25), nullable=True, primary_key=True)
    mediasite_url = Column(String(225), nullable=False)
    podcast_url = Column(String(225), nullable=True)
    navidile_url = Column(String(225), nullable=True)
    course_name = Column(String(225), nullable=False)
    date_added = Column(DateTime, nullable=False)
    folder_id = Column(String(225), nullable=True)
    pub_date = Column(String(225), nullable=False)
    cyear = Column(Integer, nullable=False)
    presenters = Column(String(255), nullable=True)
    notified_no_podcast = Column(Boolean, nullable=True)
    next_id = Column(String(225), nullable=True)
    force_recreate = Column(Boolean, nullable=False)


    def __init__(self, idno, name="", mediasite_url="", podcast_url="", navidile_url="", rec_date=None, course=None,
                 folder_id=None, pub_date=""):
        self.idno = idno
        self.name = name
        self.mediasite_url = mediasite_url
        self.podcast_url = podcast_url
        self.navidile_url = navidile_url
        self.course_name = course.name
        self.date_added = datetime.datetime.now()
        self.course_id = course.course_id
        self.pub_date = pub_date
        self.cyear = course.cyear
        self.rec_date = rec_date
        self.folder_id = folder_id
        self.presenters = None
        self.notified_no_podcast = False
        self.next_id = None
        self.force_recreate = True
        self.course_uid = course.unique_id


class Subscriber(Base):
    __tablename__ = 'subscribers'

    email_addr = Column(String(225), primary_key=True)
    last_update = Column(DateTime, nullable=True)
    subscriptions = Column(String(14), nullable=True)
    cyear = Column(Integer, nullable=True)


    def __init__(self, emailaddress, cyear, subscriptions=""):
        self.email_addr = emailaddress
        self.last_update = datetime.datetime.now()
        self.subscriptions = subscriptions
        self.cyear = cyear


class CalendarItem(Base):
    __tablename__ = 'cal_items'

    idno = Column(String(225), primary_key=True)
    name = Column(String(225), nullable=False)
    lec_id = Column(Integer, nullable=False)
    cyear = Column(Integer, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    presenters = Column(String(255), nullable=True)
    to_record = Column(Boolean, nullable=False)
    auto_number = Column(Boolean, nullable=False)
    mediasite_fldr = Column(String(255), nullable=True)
    course_uid = Column(String(25))

    def __init__(self, idno, name, start_time, end_time, course):
        self.idno = idno
        self.name = name
        self.start_time_str = start_time
        self.end_time_str = end_time
        self.presenters = None
        self.to_record = True
        self.course_uid = course.unique_id


class NavidileTask(Base):
    __tablename__ = 'aa_navidile_tasks'

    name = Column(String(225), nullable=False, primary_key=True)
    run_interval = Column(Integer, nullable=False)
    last_ran = Column(DateTime, nullable=False)
    last_error = Column(Text, nullable=True)
    last_report = Column(Text, nullable=True)
    selected_only = Column(Boolean, nullable=False)
    force_run = Column(Boolean, nullable=False)


    def __init__(self, idno, name, start_time, end_time, course):
        self.idno = idno
        self.name = name
        self.start_time_str = start_time
        self.end_time_str = end_time
        self.presenters = None
        self.to_record = True
        self.force_run = False
        self.selected_only = True


class MSClass(Base):
    __tablename__ = 'ms_class_options'

    cyear = Column(Integer, primary_key=True)
    recorder_name = Column(String(225), nullable=False)
    google_calendar_template = Column(String(225), nullable=True)
    keep_updated = Column(Boolean, nullable=False)
    notice = Column(String(500), nullable=True)
    other = Column(String(225), nullable=False)


class ZoneCalItem(Base):
    __tablename__ = 'zone_cal_items'

    idno = Column(String(225), primary_key=True)
    name = Column(String(225), nullable=False)
    start_time_str = Column(String(225), nullable=False)
    end_time_str = Column(String(225), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    location = Column(String(225), nullable=True)
    description = Column(String(2048), nullable=False)


    def __init__(self, idno, name, start_time_str, end_time_str, location, description):
        self.idno = idno
        self.name = remove_non_ascii(name)
        self.start_time_str = start_time_str
        self.end_time_str = end_time_str
        self.start_date = self.parse_date(start_time_str)
        self.end_date = self.parse_date(end_time_str)
        self.location = location
        self.description = description

    def parse_date(self, date_str):
        date_str = date_str.replace(' 0:00 am', ' 12:00 pm')
        return datetime.datetime.strptime(date_str.upper(), '%m/%d/%Y %I:%M %p')


class ScheduledRecording(Base):
    __tablename__ = 'scheduled_recordings'

    idno = Column(String(225), primary_key=True)
    lname = Column(String(225), nullable=False)
    l0name = Column(String(300), nullable=False)
    lec_id = Column(Integer, nullable=False)
    cyear = Column(Integer, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    cut_short = Column(Boolean, nullable=False)
    presenters = Column(String(255), nullable=True)
    auto_number = Column(Boolean, nullable=False)
    course_name = Column(String(225), nullable=False)
    course_uid = Column(String(25), nullable=False)
    mediasite_fldr = Column(String(255), nullable=True)
    excluded = Column(Boolean, nullable=False)
    scheduled = Column(Boolean, nullable=False)
    combined_with_another = Column(Boolean, nullable=False)
    recorded = Column(Boolean, nullable=False)
    notified_unrecorded = Column(Boolean, nullable=False)
    notified_unscheduled = Column(Boolean, nullable=False)
    folderID = Column(String(225), nullable=True)


    def __init__(self, calitem, ):
        self.idno = calitem.idno
        self.lec_id = calitem.lec_id
        self.course_name = calitem.course_name
        self.course_uid = calitem.course_uid
        self.cyear = calitem.cyear
        self.start_date = calitem.start_date
        self.end_date = calitem.end_date
        self.auto_number = calitem.auto_number
        self.mediasite_fldr = calitem.mediasite_fldr

        self.lname = remove_non_ascii(calitem.name).replace("Lecture: ", "").replace("Lecture ", "L").replace("  ", " ")
        self.l0name = "L%02d: %s" % (
            self.lec_id, calitem.name.replace("Lecture: ", "").replace("Lecture ", "").replace("  ", " "))
        self.presenters = calitem.presenters
        self.mediasite_folder = calitem.mediasite_fldr
        self.cut_short = False
        self.excluded = False
        self.scheduled = False
        self.combined_with_another = False
        self.recorded = False
        self.notified_unrecorded = False
        self.notified_unscheduled = False
        self.folderID = None

    def get_rec_end(self):
        if self.cut_short:
            return self.end_date - datetime.timedelta(minutes=3)
        return self.end_date + datetime.timedelta(minutes=15)

    def compare_overlap(self, item2):

        result = datetime.timedelta(seconds=0)
        item1 = self
        if item1.start_date < item2.start_date:
            result = item1.end_date - item2.start_date
        if item1.start_date >= item2.start_date:
            result = item1.start_date - item2.end_date
        #        if result ==datetime.timedelta(seconds=0):
        #            print self.name, item2.name
        #            print self.start_date,  self.end_date
        #            print item2.start_date, item2.end_date

        return result

    def combine(self, item2):
        self.lname = "%s; %s" % (self.lname, item2.lname)
        self.l0name = "%s; %s" % (self.l0name, item2.l0name)
        #combine presenters
        if not item2.presenters:
            item2.presenters = "Mediasite Presenter"
        if not self.presenters:
            self.presenters = "Mediasite Presenter"

        item2p = set(item2.presenters.split('; '))
        selfp = set(self.presenters.split('; ')) | item2p
        self.presenters = '; '.join(selfp)

        item2.excluded = True
        item2.combined_with_another = True

        self.end_date = item2.end_date

    def combine_as_same(self, item2):
        self.lname = "%s; %s" % (self.lname, item2.lname)
        self.l0name = "L%02d: %s" % (self.lec_id, self.lname)
        item2p = set(item2.presenters.split('; '))
        selfp = set(self.presenters.split('; ')) | item2p
        self.presenters = '; '.join(selfp)

        self.end_date = item2.end_date
        item2.excluded = True
        item2.combined_with_another = True

    def exclude(self, rec_exclude):
        for txt in rec_exclude:
            if txt in self.name:
                return True
        return False

    def short_name(self):
        if self.auto_number:
            return self.l0name
        else:
            return self.lname


Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
s = Session()

if __name__ == "__main__":
    main(sys.argv[1:])
    
