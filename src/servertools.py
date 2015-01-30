import logging
import smtplib
import os.path
import socket



def init_logger1(loggername, filename=None):
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
    if len(logger.handlers) == 0:
        logger.addHandler(ch)
        logger.addHandler(sh)
    return logger


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("yahoo.com", 80))
    (sockname, port) = s.getsockname()
    return sockname

    
def send_out(mail_from, relayto, msg, settings):
    worked = False
    logger = init_logger1('navidile4')
    hostname = socket.gethostname()
    smtp_url = settings[hostname]['email_out_url']
    port = int(settings[hostname]['email_out_port'])
    auth_reqd = False
    if 'email_out_username' in settings[hostname]:
        auth_reqd = True
        username = settings[hostname]['email_out_username']
        if 'email_out_password' in settings[hostname]:
            password = settings[hostname]['email_out_password']
        else:
            import keyring
            password = keyring.get_password(smtp_url, username)
        password = password.encode('ascii')
    try:
        server1 = smtplib.SMTP(smtp_url, port)
        if auth_reqd:
            server1.login(username, password)
        server1.sendmail(mail_from, relayto, msg.as_string())
        logger.info("sent mail to %s" % relayto[0])
        worked = True
    except smtplib.SMTPException:
        logger.warn('SMTP exception',  exc_info=1)
    return worked
