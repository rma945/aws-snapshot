import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header


class EmailSender():
    """
    email_server_config = {"server": "localhost",
                           "port": 25,
                           "tls": False}
    """
    def __init__(self, email_server_config):
        self.server_config = email_server_config

    def send_email(self, email_to, email_subject, email_text, email_attach=None):
        email_message = MIMEMultipart('alternative')
        email_message['Subject'] = Header(email_subject, 'utf-8')
        email_message['From'] = self.server_config['from']
        email_message['To'] = email_to
        email_message.attach(MIMEText(email_text.encode('utf-8'), 'plain', 'utf-8'))

        try:
            smtp_connection = smtplib.SMTP(self.server_config["server"], self.server_config["port"], 5)

            if self.server_config["tls"]:
                smtp_connection.starttls()

            smtp_connection.ehlo()
            smtp_connection.login(self.server_config["user"], self.server_config["password"])
            smtp_connection.sendmail(self.server_config['from'], email_to, email_message.as_string())
            smtp_connection.close()
        except:
            return 1
        return 0
