from urllib import urlencode
import urllib2 as urlrequest
import json


class SlackSender():
    def __init__(self, api_url=""):
        self.api_url = api_url
        self.url_opener = urlrequest.build_opener(urlrequest.HTTPHandler())

    def send_message(self, **kwargs):
        payload = kwargs
        payload_json = json.dumps(payload)
        data = urlencode({"payload": payload_json})
        req = urlrequest.Request(self.api_url)
        response = self.url_opener.open(req, data.encode('utf-8')).read()
        return response.decode('utf-8')
