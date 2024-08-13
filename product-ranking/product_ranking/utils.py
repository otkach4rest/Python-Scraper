import os
import pickle
import re
import time
import traceback
import random
import urlparse

import boto
from boto.s3.key import Key
from OpenSSL import SSL

from scrapy.conf import settings
from scrapy.contrib.downloadermiddleware.cookies import CookiesMiddleware
from scrapy.core.downloader.contextfactory import ScrapyClientContextFactory
from twisted.internet._sslverify import ClientTLSOptions
from twisted.internet.ssl import ClientContextFactory

true_args_values = (1, '1', 'true', 'True', True)
false_args_values = (0, '0', 'false', 'False', False, None)

def get_canonical_url(response):
    canonical_url = response.xpath('//link[@rel="canonical"]/@href').extract()
    if canonical_url:
        return urlparse.urljoin(response.url, canonical_url[0])

def get_random_positive_float_number():
    return round(random.uniform(0.01, 100.00), 2)

def is_empty(x, y=None):
    if x:
        return x[0]
    else:
        return y

def valid_url(url):
    if not re.findall(r"^http(s)?://", url):
        url = "http://" + url
    return url

def is_valid_url(url):
    return bool(re.findall(r"^http(s)?://", url))

def replace_http_with_https(url):
    return re.sub('^http://', 'https://', url)

def extract_first(selector_list, default=None):
    for x in selector_list:
        return x.extract()
    else:
        return default

def _init_chromium():
    from pyvirtualdisplay import Display
    from selenium import webdriver
    import socket

    socket.setdefaulttimeout(60)
    display = Display(visible=False, size=(1280, 720))
    display.start()
    executable_path = '/usr/sbin/chromedriver'
    if not os.path.exists(executable_path):
        executable_path = '/usr/local/bin/chromedriver'
    driver = webdriver.Chrome(executable_path=executable_path)
    return driver

def urlEncodeNonAscii(b):
    return re.sub('[\x80-\xFF]', lambda c: '%%%02x' % ord(c.group(0)), b)

class SharedCookies(object):

    TIMEOUT = 60

    cookies = None
    shared_cookies = None
    shared_cookies_lock = None

    def __init__(self, key, bucket='sc-settings'):
        # hook shared cookies
        middlewares = settings['DOWNLOADER_MIDDLEWARES']
        middlewares['scrapy.contrib.downloadermiddleware.cookies.CookiesMiddleware'] = None
        middlewares['product_ranking.utils.SharedCookiesMiddleware'] = 700
        settings.overrides['DOWNLOADER_MIDDLEWARES'] = middlewares

        self.bucket = bucket
        self.key = key

        try:
            s3_conn = boto.connect_s3(is_secure=False)
            s3_bucket = s3_conn.get_bucket(self.bucket, validate=False)
            self.shared_cookies = Key(s3_bucket)
            self.shared_cookies.key = '{}.cookies'.format(self.key)
            if not self.shared_cookies.exists():
                self.shared_cookies.set_contents_from_string('')

            self.shared_cookies_lock = Key(s3_bucket)
            self.shared_cookies_lock.key = '{}.lock'.format(self.key)
            if not self.shared_cookies_lock.exists():
                self.shared_cookies_lock.set_contents_from_string('')
        except:
            print(traceback.format_exc())

    def set(self, cookies):
        try:
            self.shared_cookies.set_contents_from_string(pickle.dumps(cookies))
            self.cookies = cookies

            return True
        except:
            print(traceback.format_exc())

        return False

    def get(self):
        if self.cookies:
            return self.cookies

        try:
            start_time = time.time()

            while time.time() - start_time < self.TIMEOUT:
                if not self.is_locked():
                    break

                time.sleep(1)

            content = self.shared_cookies.get_contents_as_string()
            if content:
                self.cookies = pickle.loads(self.shared_cookies.get_contents_as_string())

                return self.cookies
        except:
            print(traceback.format_exc())

        return False

    def delete(self):
        try:
            self.shared_cookies.set_contents_from_string('')
            self.cookies = None

            return True
        except:
            print(traceback.format_exc())

        return False

    def lock(self):
        try:
            self.shared_cookies_lock.set_contents_from_string('1')

            return True
        except:
            print(traceback.format_exc())

        return False

    def is_locked(self):
        try:
            if self.shared_cookies_lock.get_contents_as_string():
                return True
        except:
            print(traceback.format_exc())

        return False

    def unlock(self):
        try:
            self.shared_cookies_lock.set_contents_from_string('')

            return True
        except:
            print(traceback.format_exc())

        return False


class SharedCookiesMiddleware(CookiesMiddleware):

    def process_request(self, request, spider):
        if not spider.shared_cookies.is_locked():
            shared_cookies = spider.shared_cookies.get()

            if shared_cookies:
                self.jars = shared_cookies

        return super(SharedCookiesMiddleware, self).process_request(request, spider)

    def process_response(self, request, response, spider):
        if spider.shared_cookies.is_locked():
            spider.shared_cookies.set(self.jars)

        return super(SharedCookiesMiddleware, self).process_response(request, response, spider)


class TLSFlexibleContextFactory(ScrapyClientContextFactory):
    """A more protocol-flexible TLS/SSL context factory.

    A TLS/SSL connection established with [SSLv23_METHOD] may understand
    the SSLv3, TLSv1, TLSv1.1 and TLSv1.2 protocols.
    See https://www.openssl.org/docs/manmaster/ssl/SSL_CTX_new.html
    """

    def __init__(self):
        self.method = SSL.SSLv23_METHOD


class CustomClientContextFactory(ScrapyClientContextFactory):
    def getContext(self, hostname=None, port=None):
        ctx = ClientContextFactory.getContext(self)
        ctx.set_options(SSL.OP_ALL)
        if hostname:
            ClientTLSOptions(hostname, ctx)
        return ctx

