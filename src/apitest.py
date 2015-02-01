import nav4api
import yaml

yamlfil = 'navidile_settings.yml'
settings = yaml.load(file(yamlfile))

opener = nav4api.build_opener(settings=settings)

academic_year = 2018
courses = nav4api.courses_by_academic_year(academic_year, opener)


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
            if 'virtualHomeFolder' = folder['displayName']:

                for page in nav4api.folder_pages(course.course_id, folder['folderID'], opener):

                    try:
                        for document in nav4api.page_docs(course.course_id, folder['folderID'], page['pageID'], opener):
                            print(document)
                    except KeyError:
                        pass

    except urllib2.HTTPError:
        logger.warn('HTTPError in doc update course {0}, folder{1}:'.format(course.name, foldername), exc_info=1);


for course in courses:
    print course
    print 'hi'
