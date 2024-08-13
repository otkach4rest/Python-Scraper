import json
import random
import re
from urlparse import urljoin, urlparse
import boto
from boto.s3.key import Key
from scrapy import log, signals
from scrapy.conf import settings
from scrapy.contrib.downloadermiddleware.redirect import (MetaRefreshMiddleware,
                                                          RedirectMiddleware)
from scrapy.contrib.downloadermiddleware.retry import RetryMiddleware
from scrapy.core.downloader.handlers.http11 import TunnelError
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse
from scrapy.utils.response import get_meta_refresh, response_status_message

from incapsula_headers import (monkey_patch_scrapy_request,
                               monkey_patch_twisted_headers)


class VerizonMetaRefreshMiddleware(MetaRefreshMiddleware):
    def process_response(self, request, response, spider):
        request.meta['dont_filter'] = True
        if 'dont_redirect' in request.meta or request.method == 'HEAD' or \
                not isinstance(response, HtmlResponse) or request.meta.get('redirect_times') >= 1:
            request.meta['dont_redirect'] = True
            return response

        if isinstance(response, HtmlResponse):
            interval, url = get_meta_refresh(response)
            if url and interval < self._maxdelay:
                redirected = self._redirect_request_using_get(request, url)
                redirected.dont_filter = True
                return self._redirect(redirected, request, spider, 'meta refresh')

        return response


class VerizonRedirectMiddleware(RedirectMiddleware):
    def process_response(self, request, response, spider):
        if (request.meta.get('dont_redirect', False) or
                response.status in getattr(spider, 'handle_httpstatus_list', []) or
                response.status in request.meta.get('handle_httpstatus_list', []) or
                request.meta.get('handle_httpstatus_all', False)):
            return response

        allowed_status = (301, 302, 303, 307)
        if 'Location' not in response.headers or response.status not in allowed_status:
            return response

        # HTTP header is ascii or latin1, redirected url will be percent-encoded utf-8
        location = response.headers['location'].decode('latin1')
        search_final_location = re.search('actualUrl=(.*)', location)

        if search_final_location:
            redirected_url = urljoin(request.url, search_final_location.group(1))
        else:
            redirected_url = urljoin(request.url, location)

        if response.status in (301, 307) or request.method == 'HEAD':
            redirected = request.replace(url=redirected_url)
            return self._redirect(redirected, request, spider, response.status)

        redirected = self._redirect_request_using_get(request, redirected_url)
        return self._redirect(redirected, request, spider, response.status)


class AmazonProxyMiddleware(RetryMiddleware):

    def process_response(self, request, response, spider):
        if 'dont_retry' in request.meta:
            return response
        if response.status == 503:
            reason = response_status_message(response.status)
            request.headers['Accept-Encoding'] = 'gzip, deflate, br{}'.format(random.randint(0, 10000))
            request.headers.pop('Referer', '')
            request.headers.setdefault("Connection", "close")
            request.headers.pop('Cookie', None)
            return self._retry(request, reason, spider) or response
        return response


class ProxyFromConfig(object):
    def __init__(self, use_proxies, settings):
        self.haproxy_endpoint = None
        self.amazon_bucket_name = "sc-settings"
        self.production_bucket_config_filename = "global_proxy_config.cfg"
        self.master_bucket_config_filename = "master_proxy_config.cfg"

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('USE_PROXIES') and not crawler.settings.get('USE_PROXIES'):
            raise NotConfigured
        use_proxies = crawler.settings.getbool('USE_PROXIES')
        obj = cls(use_proxies, crawler.settings)
        crawler.signals.connect(obj.spider_opened, signal=signals.spider_opened)
        return obj

    def spider_opened(self, spider):
        try:
            with open("/tmp/branch_info.txt", "r") as gittempfile:
                all_lines = gittempfile.readlines()
                branch_name = all_lines[0].strip()
        except Exception:
            # TODO Add logging to middlewares/extensions
            # defaults to production config
            branch_name = "sc_production"
        # check for flag put there by scrapy_daemon
        if branch_name == "sc_production":
            config_filename = self.production_bucket_config_filename
        else:
            config_filename = self.master_bucket_config_filename
        full_config = self.get_proxy_config_file(self.amazon_bucket_name, config_filename)
        setattr(spider, "proxy_config_filename", str(config_filename))
        spider_name = getattr(spider, 'name')
        if full_config and spider_name:
            site = spider_name.replace("_shelf_urls_products", "").replace("_products", "")
            if site in full_config:
                spider_config = full_config.get(site, {})
            else:
                spider_config = full_config.get("default", {})
            setattr(spider, "proxy_config", str(spider_config))
            if spider_config:
                chosen_proxy = self._weighted_choice(spider_config)
                if chosen_proxy and ":" in chosen_proxy:
                    middlewares = settings.get('DOWNLOADER_MIDDLEWARES')
                    middlewares['product_ranking.scrapy_fake_useragent.middleware.RandomUserAgent'] = 400
                    middlewares['scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware'] = None
                    middlewares['product_ranking.randomproxy.RandomProxy'] = None
                    settings.overrides['DOWNLOADER_MIDDLEWARES'] = middlewares
                    self.haproxy_endpoint = "http://" + chosen_proxy
                    setattr(spider, "proxy_service", chosen_proxy)

        if not self.haproxy_endpoint:
            raise NotConfigured

    def _insert_proxy_into_request(self, request):
        request.meta['proxy'] = self.haproxy_endpoint

    def process_request(self, request, spider):
        if self.haproxy_endpoint:
            # Don't overwrite existing
            if 'proxy' in request.meta:
                return
            if not "crawlera" in self.haproxy_endpoint:
                self._insert_proxy_into_request(request)

    def process_exception(self, request, exception, spider):
        log.msg('Error {} getting url {} using {} proxy'.format(exception, request.url, self.haproxy_endpoint))

    def _weighted_choice(self, choices_dict):
        choices = [(key, value) for (key, value) in choices_dict.items()]
        # Accept dict, converts to list
        # of iterables in following format
        # [("choice1", 0.6), ("choice2", 0.2), ("choice3", 0.3)]
        # Returns chosen variant
        total = sum(w for c, w in choices)
        r = random.uniform(0, total)
        upto = 0
        for c, w in choices:
            if upto + w >= r:
                return c
            upto += w

    @staticmethod
    def get_proxy_config_file(amazon_bucket_name, bucket_config_filename):
        proxy_config = None
        try:
            S3_CONN = boto.connect_s3(is_secure=False)
            S3_BUCKET = S3_CONN.get_bucket(amazon_bucket_name, validate=False)
            k = Key(S3_BUCKET)
            k.key = bucket_config_filename
            value = k.get_contents_as_string()
            value = value.replace("\n", "").replace(" ", "").replace(",}", "}")
            proxy_config = json.loads(value)
        except Exception as e:
            print(e)
        else:
            print('Retrieved proxy config from bucket: {}'.format(value))
        return proxy_config


class IncapsulaRequestMiddleware(object):

    def __init__(self):
        monkey_patch_twisted_headers()
        monkey_patch_scrapy_request()

    def process_request(self, request, spider):
        # TODO: replace spider with request
        spider.headers['Host'] = urlparse(request.url).netloc
        for k, v in spider.headers.items():
            request.headers.setdefault(k, v)


class IncapsulaRetryMiddleware(object):

    def process_response(self, request, response, spider):
        if not response.headers.get('X-CDN'):
            incapsula_retry = request.meta.get('incapsula_retry', 0) + 1
            if incapsula_retry < 5:
                request.meta['incapsula_retry'] = incapsula_retry
                return request.replace(dont_filter=True)
        return response


class TunnelRetryMiddleware(RetryMiddleware):

    def process_exception(self, request, exception, spider):
        if (isinstance(exception, self.EXCEPTIONS_TO_RETRY) or isinstance(exception, TunnelError) ) \
                and 'dont_retry' not in request.meta:
            # TODO: remove two lines below
            if hasattr(spider, 'headers'):
                spider.headers['Connection'] = 'close'
            else:
                request.headers['Connection'] = 'close'
            return self._retry(request, exception, spider)
