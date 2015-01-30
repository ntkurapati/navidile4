import logging
import smtplib
import os.path
import ftplib
import socket
import yaml

hostname = socket.gethostname()
yamlfile = 'navidile_settings.yml'
path=os.path.dirname(os.path.abspath(__file__))
yamlfile = os.path.join(path, yamlfile)
settings = yaml.load(file(yamlfile))


def init_logger1(loggername, filename =None):
    if not filename:
        filename = os.path.join(settings[hostname]['log_loc'], loggername+'.log')
    logger = logging.getLogger(loggername)
    logger.setLevel(logging.DEBUG)
    ch = logging.FileHandler(filename)
    sh = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    # add formatter 
    ch.setFormatter(formatter)
    sh.setFormatter(formatter)
    # add ch to logger
    if len(logger.handlers)==0:
        logger.addHandler(ch)
        logger.addHandler(sh)
    return logger

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("yahoo.com",80))
    (sockname, port)=s.getsockname();
    #print s.getsockname()
    return sockname


    
def send_out( mail_from, relayto, msg, settings):
    worked=False
    LOGGER=init_logger1('navidile4'); 
    hostname = socket.gethostname()
    smtp_url =settings[hostname]['email_out_url']
    port =int(settings[hostname]['email_out_port'])
    auth_reqd = False
    if 'email_out_username' in settings[hostname]:
        auth_reqd = True
        username =settings[hostname]['email_out_username']
        if 'email_out_password' in  settings[hostname]:
            password = settings[hostname]['email_out_password']
        else:
            import keyring
            password  =keyring.get_password(smtp_url, username);
        password = password.encode('ascii')
    try:
        server1=smtplib.SMTP(smtp_url, port)
        if auth_reqd:
            server1.login(username, password)
        server1.sendmail(mail_from, relayto, msg.as_string())
        LOGGER.info("sent mail to %s" %  relayto[0])
        worked=True
    except smtplib.SMTPException:
        LOGGER.warn('SMTP exception',  exc_info=1);
    except:
        LOGGER.warn('Other exception',  exc_info=1);
    finally:
        server1.quit()
    return worked

def upload_file(settings, fileloc, destname):
    if 'upload' in settings[hostname] and not settings[hostname]['upload']:
        return
    LOGGER = logging.getLogger('navidile4')
    try:
        ftpurl = settings['ftp_server']['url'];
        ftpuser = settings['ftp_server']['username']
        ftppassword = keyring.get_password(ftpurl, ftpuser)
        s = ftplib.FTP(ftpurl, ftpuser, ftppassword)
        f = open(fileloc, 'rb')        # file to send
        s.storbinary('STOR %s' % (settings['ftp_server']['sub_dir']+destname), f)         # Send the file

        f.close()                                # Close file and FTP
        s.quit()
    except:
        LOGGER.warn('error',  exc_info=1)
        
