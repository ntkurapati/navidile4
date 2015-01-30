from __future__ import unicode_literals, print_function

import urllib2
import json
import sys

'''
nav4api.py -- Gateway into the navigator 4 API

TODO:
Convert JSON representation into object model, reconcile both
Consider converting this into a class with the urlopener as a solitary member
'''

NAV4API_URL = 'http://navapi.medschool.pitt.edu/Module'
NAV4API_COURSE_FOLDERS = NAV4API_URL + '/Course/{course}/Folder'
NAV4API_FOLDER_PAGES = NAV4API_COURSE_FOLDERS + '/{folder}/Page'
NAV4API_PAGE_DOCUMENTS = NAV4API_FOLDER_PAGES + '/{page}/Document'
NAV4API_YEAR_COURSES = NAV4API_URL + '/CourseByYear/{year}'

def courses_by_academic_year(academic_year, opener):
    url = NAV4API_YEAR_COURSES.format(year=academic_year)
    return json.loads(opener.open(url).read())

def course_folders(course_id, opener):
    url = NAV4API_COURSE_FOLDERS.format(course=course_id)
    return json.loads(opener.open(url).read())
    

def folder_pages(course_id, folder_id, opener):
    url = NAV4API_FOLDER_PAGES.format(course=course_id, folder=folder_id)
    return json.loads(opener.open(url).read())

def page_docs(course_id, folder_id, page_id, opener):
    url = NAV4API_PAGE_DOCUMENTS.format(course=course_id, folder=folder_id,
                                        page=page_id)
    return json.loads(opener.open(url).read())
        
def course_docs(course_id, opener):
    documents = []
    for folder in course_folders(course_id, opener):
        for page in folder_pages(course_id, folder['folderID'], opener):
            documents += page_docs(course_id, folder['folderID'], 
                                  page['pageID'], opener) 
    return documents
    
def build_opener(username = None, password = None, settings=None):
    '''Return a OpenerDirector with creds for HTTP Basic authentication'''
    try:
        username = username or settings['navigator']['username']
        password = password or settings['navigator']['password']
    except KeyError as e:
        raise Exception("Username and/or password not present")

    auth_handler = urllib2.HTTPBasicAuthHandler()
    auth_handler.add_password(realm='Nav4 API', uri=NAV4API_URL, 
                              user=username, passwd=password)
    return urllib2.build_opener(auth_handler)
