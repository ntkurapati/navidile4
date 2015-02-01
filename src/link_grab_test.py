__author__ = 'ntk'
import mechanize
import yaml
import logging
import urllib2
from BeautifulSoup import BeautifulSoup


def update_mediasite_urls(course, url_to_check, settings):
    if not url_to_check:
        return
    br = mechanize.Browser()
    br.set_handle_robots(False)

    try:

        br.open(url_to_check)
        response = br.response()
        response.set_data(response.get_data().replace("<br/>", "<br />"))
        br.set_response(response)
        forms = mechanize.ParseResponse(response, backwards_compat=False)
        form = forms[0]
        username = settings['navigator']['username']
        password = settings['navigator']['password']

        form['ctl00$bodyContent$txtUserName5'] = username
        form['ctl00$bodyContent$txtPassword5'] = password

        request2 = form.click()
        response2 = mechanize.urlopen(request2)

        page = response2.read()
        #page = urllib2.urlopen(page_url).read()
        soup = BeautifulSoup(page)
        print page
        for incident in soup('a'):
            if 'mediasite in ':
                course.mediasite_url = incident['href']
                logger.info('Added mediasite url for {0}: {1}'.format(course.name, incident['href']))
        for incident in soup('a', title='Podcast RSS'):
            if not course.podcast_url:
                course.podcast_url = incident['href']
                logger.info('Added podcast url for {0}: {1}'.format(course.name, incident['href']))
    except IOError, e:
        logger.warn('Couldn''t access this url...: {0} {1}'.format(course.name, url_to_check), exc_info=1)
        course.last_error = str(e)
    except Exception, e:
        logger.warn('HTTPError:{0}'.format(course.name), exc_info=1)
        course.last_error = str(e)


class Course:
    def __init__(self):
        pass


def main(_):
    global logger
    logger = logging.getLogger('navidile_linkgrabtest')
    logger.setLevel(logging.DEBUG)
    sh = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    course = Course()
    course.navigator_url = "https://navigator.medschool.pitt.edu/curriculum/course/1994327999"
    course.name = "Blah"
    settings = yaml.load(file('navidile_settings.yml'))
    update_mediasite_urls(course, settings)

main('test')