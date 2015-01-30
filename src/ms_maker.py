# Makes a mediasite schedule from a given "*.cal" file

import datetime
import pytz
import nameparser
import sys

TIMEZONE = 'US/Eastern'

header = """<?xml version="1.0" encoding="utf-8" ?>
<RecorderScheduleImport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <RecorderSchedules>
"""
footer = """
  </RecorderSchedules>
</RecorderScheduleImport>
"""

presenter_boilerplate = """
           <PresenterName>
            <FirstName>Mediasite</FirstName>
            <MiddleName/>
            <LastName>Presenter</LastName>
          </PresenterName>"""

presenter_template = """
           <PresenterName>
            <FirstName>{FIRSTNAME}</FirstName>
            <MiddleName/>
            <LastName>{LASTNAME}</LastName>
          </PresenterName>"""

recorder_sched = """
    <RecorderSchedule>
      <PresentationTemplateOverride>
        <PresentationTitle>{PRESENTATIONTITLE}</PresentationTitle>
        <PlayerName>PittSOM - Standard Video - Standard Slides</PlayerName>
        <FolderName>{FOLDERNAME}</FolderName>
        <PresenterNames>
{PRESENTERS}
        </PresenterNames>
      </PresentationTemplateOverride>
      <RecorderName>{RECORDERNAME}</RecorderName>
      <PresentationNamingFormat>ScheduleNameOnly</PresentationNamingFormat>
      <AdvanceCreationTimeInMinutes>10080</AdvanceCreationTimeInMinutes>
      <AdvanceLoadTimeInMinutes>14</AdvanceLoadTimeInMinutes>
      <ScheduledOperations>CreateLoadStartStop</ScheduledOperations>
      <NotifyPresenters>true</NotifyPresenters>
      <NotificationEmailAddresses>
        <NotificationEmailAddress>scheduler@students.medschool.pitt.edu</NotificationEmailAddress>
      </NotificationEmailAddresses>
      <DeleteInactive>false</DeleteInactive>
      <Recurrences>
        <Recurrence>
          <BeginDateTime>{BEGINDATE}</BeginDateTime>
          <EndDateTime>{ENDDATE}</EndDateTime>
          <RecordingDurationInMinutes>{DURATION}</RecordingDurationInMinutes>
          <AlwaysExcludeHolidays>false</AlwaysExcludeHolidays>
        </Recurrence>
      </Recurrences>
    </RecorderSchedule>
"""

# Formats the person's name in an XML friendly format
def xmlformatname(pname):
    name = nameparser.HumanName(pname)
    if (not name.first) or (not name.last):
        return None
    return presenter_template.format(FIRSTNAME=html_escape(name.first), LASTNAME=html_escape(name.last))


# Removes crappy non-ascii unicode letters which cause problems in python
def removeNonAscii(s):
    output = ''.join([x for x in s if ord(x) < 128])
    return output.replace(u'\u2013', '-').replace(u'\u2019', '').replace(u'\u2014', '')


# Makes an xml file for the recorder with the given list of calender items
def make_xml(cal_items, filename, recordername="Lecture Room 2"):
    # mediasite_id = course_dict['mediasite_id']
    elements = []
    elements.append(header)
    # iterate through cal items
    for item in cal_items:
        # convert recording start to UTC time
        begindate = dt_to_utc_ts(item.start_date)

        # exclude calendar items that occur before today
        if item.start_date < datetime.datetime.now():
            continue
        # nextmonday = datetime.datetime.now() + datetime.timedelta(days=-datetime.datetime.now().weekday(), weeks=1)

        # convert recording end to UTC time
        enddate = dt_to_utc_ts(item.start_date + datetime.timedelta(minutes=36 * 60) - datetime.timedelta(minutes=60))
        # rec_sched = ''.join(recorder_sched)


        presentersxml = []
        # Parse presenter names
        if item.presenters:
            for pname in item.presenters.split('; '):

                xmlformatted = xmlformatname(pname)
                if xmlformatted and xmlformatted not in presentersxml:
                    presentersxml.append(xmlformatted)
        if len(presentersxml) == 0:
            presentersxml.append(presenter_boilerplate)

        rec_sched = recorder_sched.format(PRESENTATIONTITLE=html_escape(item.short_name()),
                                          PRESENTERS=''.join(presentersxml),
                                          FOLDERNAME=html_escape(item.mediasite_fldr),
                                          RECORDERNAME=html_escape(recordername), BEGINDATE=begindate, ENDDATE=enddate,
                                          DURATION=(item.get_rec_end() - item.start_date).seconds / 60)

        elements.append(rec_sched)
    elements.append(footer)
    completestring = ''.join(elements)
    # save to disk
    f1 = open(filename, 'w')

    f1.write(removeNonAscii(completestring));
    f1.close()


html_escape_table = {
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
    ">": "&gt;",
    "<": "&lt;",
}


def html_escape(text):
    text2 = text.encode('utf8')
    if text2 != text:
        print "i hate this string(causes unicode errors):" + text2
    return "".join(html_escape_table.get(c, c) for c in text2)


# Converts python datetime to mediasite xml friendly time
def dt_to_utc_ts(naivedate):
    eastern = pytz.timezone(TIMEZONE)
    loc_dt = eastern.localize(naivedate)
    # utc = pytz.utc
    # return loc_dt.astimezone(utc)
    # return loc_dt.strftime("%Y-%m-%dT%H_%M_%S%z").replace('_',':').replace('-0400', '-04:00').replace('-0500', '-05:00')
    return loc_dt.isoformat()

