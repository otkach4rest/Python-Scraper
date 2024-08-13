# ~~coding=utf-8~~
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
import json
import random
import re
import string
import urlparse
from urllib import unquote
import traceback

import lxml.html
import requests
from scrapy.conf import settings
from scrapy.http import Request
from scrapy.http.request.form import FormRequest
from scrapy.log import DEBUG, ERROR, INFO, WARNING, msg

from product_ranking.guess_brand import guess_brand_from_first_words, find_brand
from product_ranking.items import Price, SiteProductItem
from product_ranking.spiders import (FLOATING_POINT_RGEX, BaseProductsSpider,
                                     FormatterWithDefaults, cond_set_value)
from product_ranking.utils import is_empty, is_valid_url
from spiders_shared_code.amazon_variants import AmazonVariants

try:
    from captcha_solver import CaptchaBreakerWrapper
except ImportError as e:
    import sys

    print(
        "### Failed to import CaptchaBreaker.",
        "Will continue without solving captchas:",
        e,
        file=sys.stderr
    )


    class FakeCaptchaBreaker(object):
        @staticmethod
        def solve_captcha(url):
            msg("No CaptchaBreaker to solve: %s" % url, level=WARNING)
            return None


    CaptchaBreakerWrapper = FakeCaptchaBreaker


class AmazonBaseClass(BaseProductsSpider):
    buyer_reviews_stars = ['one_star', 'two_star', 'three_star', 'four_star',
                           'five_star']

    SEARCH_URL = 'https://{domain}/s/ref=nb_sb_noss_1?url=field-keywords={search_term}'

    REVIEW_DATE_URL = 'https://{domain}/product-reviews/{product_id}/' \
                      'ref=cm_cr_pr_top_recent?ie=UTF8&showViewpoints=0&' \
                      'sortBy=bySubmissionDateDescending&reviewerType=all_reviews'
    REVIEW_URL_1 = 'https://{domain}/ss/customer-reviews/ajax/reviews/get/' \
                   'ref=cm_cr_pr_viewopt_sr'
    REVIEW_URL_2 = 'https://{domain}/product-reviews/{product_id}/' \
                   'ref=acr_dpx_see_all?ie=UTF8&showViewpoints=1'

    handle_httpstatus_list = [404, 443]

    AMAZON_PRIME_URL = 'https://www.amazon.com/gp/product/du' \
                       '/bbop-ms3-ajax-endpoint.html?ASIN={0}&merchantID={1}' \
                       '&bbopruleID=Acquisition_AddToCart_PrimeBasicFreeTrial' \
                       'UpsellEligible&sbbopruleID=Acquisition_AddToCart_' \
                       'PrimeBasicFreeTrialUpsellEligible&deliveryOptions=' \
                       '%5Bsame-us%2Cnext%2Csecond%2Cstd-n-us%2Csss-us%5D' \
                       '&preorder=false&releaseDateDeliveryEligible=false'

    MKTP_USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_3) AppleWebKit/601.4.4 (KHTML, like Gecko) Version/9.0.3 Safari/601.4.4',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36',
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:44.0) Gecko/20100101 Firefox/44.0',
        'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.109 Safari/537.36'
    ]

    def __init__(self, captcha_retries='10', *args, **kwargs):
        middlewares = settings.get('DOWNLOADER_MIDDLEWARES')
        # We should remove two lines above, if the issue will be fixed by new headers - still 503
        middlewares['product_ranking.custom_middlewares.AmazonProxyMiddleware'] = 750
        middlewares['product_ranking.custom_middlewares.TunnelRetryMiddleware'] = 2
        middlewares['product_ranking.randomproxy.RandomProxy'] = None
        settings.overrides['DOWNLOADER_MIDDLEWARES'] = middlewares
        settings.overrides['RETRY_HTTP_CODES'] = [500, 502, 503, 504, 400, 403, 404, 408, 443]
        settings.overrides['REFERER_ENABLED'] = False
        settings.overrides['DOWNLOAD_DELAY'] = 1
        settings.overrides['CONCURRENT_REQUESTS'] = 2

        settings.overrides['DEFAULT_REQUEST_HEADERS'] = dict(
            [
                ('Accept-Encoding', 'gzip, deflate'),
                ('Accept-Language', 'ru-RU,ru;q=0.8,en-US;q=0.6,en;q=0.4'),
                ('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36'),
                ('Accept','text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'),
                ('Connection', 'keep-alive')
            ]
        )

        pipelines = settings.get('ITEM_PIPELINES')
        pipelines['product_ranking.pipelines.FillPriceFieldIfEmpty'] = 300
        settings.overrides['ITEM_PIPELINES'] = pipelines

        # this turns off crawlera per-request
        # settings.overrides['USE_PROXIES'] = True
        super(AmazonBaseClass, self).__init__(
            site_name=self.allowed_domains[0],
            url_formatter=FormatterWithDefaults(
                domain=self.allowed_domains[0]
            ),
            *args, **kwargs)

        self.captcha_retries = int(captcha_retries)
        self._cbw = CaptchaBreakerWrapper()
        self.ignore_variant_data = kwargs.get('ignore_variant_data', None)
        if self.ignore_variant_data in ('1', True, 'true', 'True') or self.summary or not self.scrape_variants_with_extra_requests:
            self.ignore_variant_data = True
        else:
            self.ignore_variant_data = False

        self.search_alias = kwargs.get('search_alias', 'aps')
        self.SEARCH_URL += "&search-alias={}".format(self.search_alias)

        self.zip_code = kwargs.get('zip_code', '94117')

        # temporary
        ITEM_PIPELINES = settings.get('ITEM_PIPELINES')
        ITEM_PIPELINES['product_ranking.pipelines.PriceSimulator'] = 300

    def _is_empty(self, x, y=None):
        return x[0] if x else y

    def _get_int_from_string(self, num):
        if num:
            num = re.findall(
                r'(\d+)',
                num
            )

            try:
                num = int(''.join(num))
                return num
            except ValueError as exc:
                self.log("Error to parse string value to int: {exc}".format(
                    exc=exc
                ), ERROR)

        return 0

    def _get_float_from_string(self, num):
        if num:
            num = self._is_empty(
                re.findall(
                    FLOATING_POINT_RGEX,
                    num
                ), 0.00
            )
            try:
                num = float(num.replace(',', '.'))
            except ValueError as exc:
                self.log("Error to parse string value to int: {exc}".format(
                    exc=exc
                ), ERROR)

        return num

    def _scrape_total_matches(self, response):
        """
        Overrides BaseProductsSpider method to scrape total result matches. total_matches_str
        and total_matches_re need to be set for every concrete amazon spider.
        :param response:
        :return: Number of total matches (int)
        """
        total_match_not_found_re = getattr(self, 'total_match_not_found_re', None)
        total_matches_re = getattr(self, 'total_matches_re', None)

        if not total_match_not_found_re and not total_matches_re:
            self.log('Either total_match_not_found_re or total_matches_re '
                     'is not defined. Or both.', ERROR)
            return None

        if unicode(total_match_not_found_re) in response.body_as_unicode():
            return 0

        count_matches = self._is_empty(
            response.xpath(
                '//*[@id="s-result-count"]/text()'
            ).re(unicode(self.total_matches_re))
        )

        total_matches = self._get_int_from_string(count_matches)

        return total_matches

    def _scrape_results_per_page(self, response):
        num = response.xpath(
            '//*[@id="s-result-count"]/text()').re('1-(\d+) of')
        if num:
            return int(num[0])
        else:
            num = response.xpath(
                '//*[@id="s-result-count"]/text()').re('(\d+) results')
            if num:
                return int(num[0])

        return None

    def _scrape_next_results_page_link(self, response):
        """
        Overrides BaseProductsSpider method to get link on next page of products.
        """
        next_pages = response.xpath('//*[@id="pagnNextLink"]/@href |'
                                    '//ul[contains(@class, "a-pagination")]'
                                    '/a[contains(text(), "eiter")]/@href').extract()
        next_page_url = None

        if len(next_pages) == 1:
            next_page_url = next_pages[0]
        elif len(next_pages) > 1:
            self.log("Found more than one 'next page' link.", ERROR)

        return next_page_url

    def _scrape_product_links(self, response):
        """
        Overrides BaseProductsSpider method to scrape product links.
        """
        lis = response.xpath(
            "//div[@id='resultsCol']/./ul/li |"
            "//div[@id='mainResults']/.//ul/li [contains(@id, 'result')] |"
            "//div[@id='atfResults']/.//ul/li[contains(@id, 'result')] |"
            "//div[@id='mainResults']/.//div[contains(@id, 'result')] |"
            "//div[@id='btfResults']//ul/li[contains(@id, 'result')]")
        links = []
        last_idx = -1

        for li in lis:
            is_prime = li.xpath(
                "*/descendant::i[contains(concat(' ', @class, ' '),"
                "' a-icon-prime ')] |"
                ".//span[contains(@class, 'sprPrime')]"
            )
            is_prime_pantry = li.xpath(
                "*/descendant::i[contains(concat(' ',@class,' '),'"
                "a-icon-prime-pantry ')]"
            )
            data_asin = self._is_empty(
                li.xpath('@id').extract()
            )

            is_sponsored = bool(li.xpath('.//h5[contains(text(), "ponsored")]').extract())

            try:
                idx = int(self._is_empty(
                    re.findall(r'\d+', data_asin)
                ))
            except ValueError:
                continue

            if idx > last_idx:
                link = self._is_empty(
                    li.xpath(
                        ".//a[contains(@class,'s-access-detail-page')]/@href |"
                        ".//h3[@class='newaps']/a/@href"
                    ).extract()
                )
                if not link:
                    continue

                if 'slredirect' in link:
                    link = 'http://' + self.allowed_domains[0] + '/' + link

                links.append((link, is_prime, is_prime_pantry, is_sponsored))
            else:
                break

            last_idx = idx

        if not links:
            self.log("Found no product links.", WARNING)

        if links:
            for link, is_prime, is_prime_pantry, is_sponsored in links:
                prime = None
                if is_prime:
                    prime = 'Prime'
                if is_prime_pantry:
                    prime = 'PrimePantry'
                prod = SiteProductItem()
                yield Request(link, callback=self.parse_product,
                              headers={'Referer': None},
                              meta={'product': prod}), prod

    def _parse_single_product(self, response):
        """
        Method from BaseProductsSpider. Enables single url mode.
        """
        return self.parse_product(response)

    def _get_products(self, response):
        """
        Method from BaseProductsSpider.
        """
        result = super(AmazonBaseClass, self)._get_products(response)

        for r in result:
            if isinstance(r, Request):
                r = r.replace(dont_filter=True)
            yield r

    def parse(self, response):
        """
        Main parsing method from BaseProductsSpider.
        """
        if self._has_captcha(response):
            result = self._handle_captcha(response, self.parse)
        else:
            result = super(AmazonBaseClass, self).parse(response)

        return result

    def parse_product(self, response):
        # TODO: refactor it
        meta = response.meta.copy()
        product = meta['product']

        if response.status == 404:
            product['response_code'] = 404
            product['not_found'] = True
            return product

        if 'the Web address you entered is not a functioning page on our site' \
                in response.body_as_unicode().lower():
            product['not_found'] = True
            return product

        if self._has_captcha(response):
            return self._handle_captcha(
                response,
                self.parse_product
            )
        elif response.meta.get('captch_solve_try', 0) >= self.captcha_retries:
            product = response.meta['product']
            self.log("Giving up on trying to solve the captcha challenge after"
                     " %s tries for: %s" % (self.captcha_retries, product['url']),
                     level=WARNING)
            return None

        if not response.meta.get('search_term') and not response.meta.get('is_prime_pantry_zip_code') \
                and self.allowed_domains[0] == 'www.amazon.com' and self._is_prime_pantry_product(response):
            product['zip_code'] = self.zip_code
            return self._build_prime_pantry_zip_request(response.request, self.zip_code)

        variants = self._parse_variants(response)
        swatches = self._parse_swatches(response)

        product_list = []
        image_urls = []

        if variants:
            for variant in variants:
                prod = SiteProductItem()
                variant_url = variant.get('url')
                variant_asin = variant.get('asin')
                variant_in_stock = variant.get('in_stock')
                if variant_in_stock:
                    availability = "In Stock"
                else:
                    availability = "Out of Stock"

                try:
                    if variant.get('properties')['Size'] == "White":
                        variant_size = " "
                    else:
                        variant_size = variant.get('properties')['Size']
                except:
                    variant_size = " "
                try:
                    variant_color = variant.get('properties')['Color']
                except:
                    variant_color = " "

                variant_price = variant.get('price')

                variant_images = swatches.get((variant_size + " " + variant_color).strip())

                if variant_images:
                    for variant_image in variant_images:
                        variant_image_url = variant_image.get('large')
                        image_urls.append(variant_image_url)

                cond_set_value(prod, 'image_urls', image_urls)
                cond_set_value(prod, 'url', variant_url)
                cond_set_value(prod, 'asin', variant_asin)
                cond_set_value(prod, 'availability', availability)
                cond_set_value(prod, 'size', variant_size)
                cond_set_value(prod, 'color', variant_color)
                cond_set_value(prod, 'price', variant_price)

                # Set prod ID
                product_id = self._parse_product_id(response.url)
                cond_set_value(response.meta, 'product_id', product_id)

                # Parse title
                title = self._parse_title(response)
                cond_set_value(prod, 'title', title)

                # Parse Categories
                category_full_info = " "
                category_list = self._parse_category(response)
                if category_list:
                    for i, categories in enumerate(category_list):
                        if i in [0, len(category_list)]:
                            category_full_info = category_full_info + categories.get('name')
                        else:
                            category_full_info = category_full_info + " > " + categories.get('name')
                cond_set_value(prod, 'categories', category_full_info)

                # Parse brand
                brand = self._parse_brand(response)
                cond_set_value(prod, 'brand', brand)

                # Parse model
                model = self._parse_model(response)
                cond_set_value(prod, 'part', model, conv=string.strip)

                # Parse parent asin
                parent_asin = self._extract_parent_asin(response)
                cond_set_value(prod, 'parent_asin', parent_asin)

                # Parse description
                description = self._parse_description(response)
                cond_set_value(prod, 'description', description)

                description_html = self._parse_description_html(response)
                cond_set_value(prod, 'description_html', description_html)

                # if variant_url and variant_price:
                #     if image_urls:
                if variant_url:
                    product_list.append(prod)

            return product_list

        else:
            canonical_url = response.xpath('//link[@rel="canonical"]/@href').extract()
            if canonical_url:
                product_url = urlparse.urljoin(response.url, canonical_url[0])
                cond_set_value(product, 'url', product_url)

            asin = self._parse_asin(response)
            cond_set_value(product, 'asin', asin)

            if product.get('no_longer_available'):
                in_stock = False
                availability = "Out of Stock"
            else:
                in_stock = True
                availability = "In Stock"
            cond_set_value(product, 'availability', availability)

            # Parse product size
            size = self._parse_product_size(response)
            cond_set_value(product, 'size', size)

            # Parse product color
            color = self._parse_product_color(response)
            if "Avoid area near eyes" in color:
                color = " "
            if "Please read all ingredients" in color:
                color = " "
            cond_set_value(product, 'color', color)

            # Set product ID
            product_id = self._parse_product_id(response.url)
            cond_set_value(response.meta, 'product_id', product_id)

            # Parse title
            title = self._parse_title(response)
            cond_set_value(product, 'title', title)

            # Parse Categories
            category_full_info = " "
            category_list = self._parse_category(response)
            if category_list:
                for i, categories in enumerate(category_list):
                    if i in [0, len(category_list)]:
                        category_full_info = category_full_info + categories.get('name')
                    else:
                        category_full_info = category_full_info + " > " + categories.get('name')
            cond_set_value(product, 'categories', category_full_info)

            # Parse brand
            brand = self._parse_brand(response)
            cond_set_value(product, 'brand', brand)

            # Parse model
            model = self._parse_model(response)
            cond_set_value(product, 'part', model, conv=string.strip)

            # Parse parent asin
            parent_asin = self._extract_parent_asin(response)
            cond_set_value(product, 'parent_asin', parent_asin)

            # Parse price
            price = self._parse_price(response)
            if price:
                cond_set_value(product, 'price', price.replace('$', ''))

            # Parse price_after_coupon
            if price and product.get("coupon_value"):
                coupon_value = product.get("coupon_value")
                if product.get('coupon_currency') == '%':
                    coupon_value = coupon_value * price / 100.0
                cond_set_value(product, 'price_after_coupon', round(price - coupon_value, 2))

            # Parse image urls
            image_urls = self._parse_image_url(response)
            product['image_urls'] = image_urls

            # Parse description
            description = self._parse_description(response)
            cond_set_value(product, 'description', description)

            description_html = self._parse_description_html(response)
            cond_set_value(product, 'description_html', description_html)

            product_list.append(product)

        for product in product_list:
            return product

    def _parse_description_html(self, response, add_xpath=None):
        """
        Parses product description.
        :param add_xpath: Additional xpathes, so you don't need to change base class
        """
        xpathes = '//*[contains(@class, "productDescriptionWrapper")] |' \
                  '//div[@id="descriptionAndDetails"] |' \
                  '//div[@id="feature-bullets"] |' \
                  '//div[@id="ps-content"] |' \
                  '//div[@id="productDescription_feature_div"] |' \
                  '//div[contains(@class, "dv-simple-synopsis")] |' \
                  '//div[@class="bucket"]/div[@class="content"] |' \
                  '//div[@id="bookDescription_feature_div"]/noscript'

        if add_xpath:
            xpathes += ' |' + add_xpath

        description = self._is_empty(response.xpath(xpathes).extract())
        if not description:
            description = self._is_empty(
                response.css('#featurebullets_feature_div').extract())
        if not description:
            iframe_content = re.findall(
                r'var iframeContent = "(.*)"', response.body
            )
            if iframe_content:
                res = iframe_content[0]
                f = re.findall('body%3E%0A%20%20(.*)'
                               '%0A%20%20%3C%2Fbody%3E%0A%3C%2Fhtml%3E%0A', res)
                if f:
                    desc = unquote(f[0])
                    description = desc

        if isinstance(description, (list, tuple)):
            description = description[0]
        return description.strip() if description else None

    def _parse_no_longer_available(self, response):
        if response.xpath('//*[contains(@id, "availability")]'
                          '//*[contains(text(), "navailable")]'):  # Unavailable or unavailable
            return True
        if response.xpath('//*[contains(@id, "outOfStock")]'
                          '//*[contains(text(), "navailable")]'):  # Unavailable or unavailable
            return True
        if response.xpath('//*[contains(@class, "availRed")]'
                          '[contains(text(), "navailable")]'):
            return True

    @staticmethod
    def _extract_group_id(response):
        group_id = response.xpath('//script[@type="text/javascript"]/text()').re('"productGroupID"\s*:\s*"(.+?)"')
        return group_id[0] if group_id else None

    @staticmethod
    def _extract_store_id(response):
        store_id = response.xpath('//input[@id="storeID" and @name="storeID"]/@value').extract()
        return store_id[0] if store_id else None

    def _parse_coupon(self, response):
        coupon_elem = response.xpath("//div[@id='couponFeature']//a[@role='button']/@title")
        coupon = coupon_elem.re('\s(.)(\d+\.\d+)\s')
        if coupon_elem and not coupon:
            coupon = coupon_elem.re('\s(\d+)(%)\s')[::-1]

        if coupon:
            try:
                coupon_currency = coupon[0]
                coupon_value = float(coupon[1])
            except Exception as e:
                self.log("Can't extract coupon {}".format(traceback.format_exc()), WARNING)
            else:
                return coupon_currency, coupon_value

    @staticmethod
    def _parse_product_id(url):
        prod_id = re.findall(r'/dp?/(\w+)|product/(\w+)/', url)
        if not prod_id:
            prod_id = re.findall(r'/dp?/(\w+)|product/(\w+)', url)
        if not prod_id:
            prod_id = re.findall(r'([A-Z0-9]{4,20})', url)
        if isinstance(prod_id, (list, tuple)):
            prod_id = [s for s in prod_id if s][0]
        if isinstance(prod_id, (list, tuple)):
            prod_id = [s for s in prod_id if s][0]
        return prod_id

    def _parse_category(self, response):
        cat = response.xpath(
            '//span[@class="a-list-item"]/'
            'a[@class="a-link-normal a-color-tertiary"]')
        if not cat:
            cat = response.xpath('//li[@class="breadcrumb"]/a[@class="breadcrumb-link"]')
        if not cat:
            cat = response.xpath('.//*[@id="nav-subnav"]/a[@class="nav-a nav-b"]')

        categories_full_info = []
        for cat_sel in cat:
            c_url = cat_sel.xpath("./@href").extract()
            c_url = urlparse.urljoin(response.url, c_url[0]) if c_url else None
            c_text = cat_sel.xpath(".//text()").extract()
            c_text = c_text[0].strip() if c_text else None
            categories_full_info.append({"url": c_url,
                                         "name": c_text})

        if categories_full_info:
            return categories_full_info
        else:
            return self._extract_department(response)

    @staticmethod
    def _extract_department(response):
        # I didn't find more elegant way
        department = response.xpath(
            '//select[@class="nav-search-dropdown searchSelect"]/option[@selected="selected"]'
        )
        if department:
            department = department[0]

            value = department.xpath('@value').extract()
            value = value[0] if value else ''

            name = department.xpath('text()').extract()
            name = name[0] if name else None

            if re.search('node=\d+', value):
                path = '/b/?ie=UTF8&{}'
            else:
                path = '/s/?{}'
            url = urlparse.urljoin(response.url, path.format(value))
            return [{'url': url, 'name': name}]

    def _parse_title(self, response, add_xpath=None):
        """
        Parses product title.
        :param response:
        :param add_xpath: Additional xpathes, so you don't need to change base class
        :return: Number of total matches (int)
        """
        xpathes = '//span[@id="productTitle"]/text()[normalize-space()] |' \
                  '//div[@class="buying"]/h1/span[@id="btAsinTitle"]/text()[normalize-space()] |' \
                  '//div[@id="title_feature_div"]/h1/text()[normalize-space()] |' \
                  '//div[@id="title_row"]/span/h1/text()[normalize-space()] |' \
                  '//h1[@id="aiv-content-title"]/text()[normalize-space()] |' \
                  '//div[@id="item_name"]/text()[normalize-space()] |' \
                  '//h1[@class="parseasinTitle"]/span[@id="btAsinTitle"]' \
                  '/span/text()[normalize-space()] |' \
                  '//*[@id="title"]/text()[normalize-space()] |' \
                  '//*[@id="product-title"]/text()[normalize-space()]'
        if add_xpath:
            xpathes += ' |' + add_xpath
            xpathes += ' |' + add_xpath

        title = self._is_empty(
            response.xpath(xpathes).extract(), ''
        ).strip()

        if not title:
            # Create title from parts
            parts = response.xpath(
                '//div[@id="mnbaProductTitleAndYear"]/span/text()'
            ).extract()
            title = ' '.join([p.strip() for p in parts if p])

        if not title:
            title = self._is_empty(response.css('#ebooksProductTitle ::text').extract(), '').strip()

        return title

    def _parse_product_color(self, response, add_xpath=None):

        colors = " "
        color_list = response.xpath("//div[@class='tooltip']//img/@alt").extract()
        if color_list:
            for color in color_list:
                colors = color.strip() + " , " + colors
        if not color_list:
            color_list = response.xpath("//table[@id='technicalSpecifications_section_1']//tr//td//text()").extract()
            if color_list:
                colors = color_list[4].strip()
        if not color_list:
            colors = " "

        return colors

    def _parse_product_size(self, response, add_xpath=None):

        sizes = " "
        size_list = response.xpath('//select[@name="dropdown_selected_size_name"]//'
                                   'option[contains(@id, "native_size_name")]//text()').extract()
        if size_list:
            for size in size_list[1:]:
                sizes = size.strip() + " , " + sizes
        else:
            sizes = " "

        return sizes

    def _parse_image_url(self, response, add_xpath=None):

        main_image_list = []
        image_list = []

        xpathes = '//div[@class="main-image-inner-wrapper"]/img/@src |' \
                  '//div[@id="coverArt_feature_div"]//img/@src |' \
                  '//div[@id="img-canvas"]/img/@src |' \
                  '//div[@class="dp-meta-icon-container"]/img/@src |' \
                  '//input[@id="mocaGlamorImageUrl"]/@value |' \
                  '//div[@class="egcProdImageContainer"]' \
                  '/img[@class="egcDesignPreviewBG"]/@src |' \
                  '//img[@id="main-image"]/@src |' \
                  '//*[@id="imgTagWrapperId"]/.//img/@data-old-hires |' \
                  '//img[@id="imgBlkFront"]/@src |' \
                  '//img[@class="masrw-main-image"]/@src'
        if add_xpath:
            xpathes += ' |' + add_xpath

        image = self._is_empty(
            response.xpath(xpathes).extract(), ''
        )

        if not image:
            # Another try to parse img_url: from html body as JS data
            img_re = self._is_empty(
                re.findall(
                    r"'colorImages':\s*\{\s*'initial':\s*(.*)\},|colorImages\s*=\s*\{\s*\"initial\":\s*(.*)\}",
                    response.body), ''
            )

            img_re = self._is_empty(list(img_re))

            if img_re:
                try:
                    res = json.loads(img_re)
                    image = res[0]['large']
                except Exception as exc:
                    self.log('Unable to parse image url from JS on {url}: {exc}'.format(
                        url=response.url, exc=exc), WARNING)

        if not image:
            # Images are not always on the same spot...
            img_jsons = response.xpath(
                '//*[@id="landingImage"]/@data-a-dynamic-image'
            ).extract()

            if img_jsons:
                img_data = json.loads(img_jsons[0])
                image = max(img_data.items(), key=lambda (_, size): size[0])

        if not image:
            image = response.xpath('//*[contains(@id, "ebooks-img-canvas")]//@src').extract()
            if image:
                image = image[0]
            else:
                image = None

        if image and 'base64' in image:
            img_jsons = response.xpath(
                '//*[@id="imgBlkFront"]/@data-a-dynamic-image | '
                '//*[@id="landingImage"]/@data-a-dynamic-image'
            ).extract()

            if img_jsons:
                img_data = json.loads(img_jsons[0])

                image = max(img_data.items(), key=lambda (_, size): size[0])[0]

        if image:
            main_image_list.append(image)

        images = response.xpath("//li[contains(@class, 'a-spacing-small')]//span//img/@src").extract()
        if not images:
            images = response.xpath(
                '//div[@id="imageBlockThumbs"]//div[contains(@class, "a-column")]//img/@src').extract()
        if not images:
            images = response.xpath(
                '//div[@class="main-image-inner-wrapper"]/img/@src').extract()

        if not images:
            images = response.xpath(
                '//div[@id="coverArt_feature_div"]//img/@src').extract()

        if not images:
            images = response.xpath(
                '//div[@id="img-canvas"]/img/@src').extract()

        if not images:
            images = response.xpath(
                '//div[@class="dp-meta-icon-container"]/img/@src').extract()

        if not images:
            images = response.xpath(
                '//div[@class="egcProdImageContainer"]/img[@class="egcDesignPreviewBG"]/@src').extract()

        if not images:
            images = response.xpath(
                '//img[@id="main-image"]/@src').extract()

        if not images:
            images = response.xpath(
                '//img[@class="masrw-main-image"]/@src').extract()

        if not images:
            images = response.xpath('//div[@class="a2s-image-block"]//img/@src').extract()

        if images:
            for image in images:
                if 'https' in image:
                    image_list.append(image)

        return image_list

    def _parse_available(self, response):
        if response.xpath('//*[contains(@id, "availability")]'
                          '//*[contains(text(), "navailable")]'):  # Unavailable or unavailable
            return False
        if response.xpath('//*[contains(@id, "outOfStock")]'
                          '//*[contains(text(), "navailable")]'):  # Unavailable or unavailable
            return False
        if response.xpath('//*[contains(@class, "availRed")]'
                          '[contains(text(), "navailable")]'):
            return False

    @staticmethod
    def _parse_brand(response, add_xpath=None):
        """
        Parses product brand.
        :param add_xpath: Additional xpathes, so you don't need to change base class
        """
        xpathes = '//*[@id="brand"]/text() |' \
                  '//*[contains(@class, "contributorNameID")]/text() |' \
                  '//*[contains(@id, "contributorName")]/text() |' \
                  '//*[@id="bylineContributor"]/text() |' \
                  '//*[@id="contributorLink"]/text() |' \
                  '//*[@id="by-line"]/.//a/text() |' \
                  '//*[@id="artist-container"]/.//a/text() |' \
                  '//div[@class="buying"]/.//a[contains(@href, "search-type=ss")]/text() |' \
                  '//a[@id="ProductInfoArtistLink"]/text() |' \
                  '//a[contains(@href, "field-author")]/text() |' \
                  '//a[@id="bylineInfo"]/text()'

        if add_xpath:
            xpathes += ' |' + add_xpath

        product = response.meta['product']
        title = product.get('title', '')

        brand = response.xpath(xpathes).extract()
        brand = is_empty([b for b in brand if b.strip()])

        if brand and (u'®' in brand):
            brand = brand.replace(u'®', '')

        if not brand:
            brand = is_empty(
                response.xpath('//a[@id="brand"]/@href').re("\/([A-Z0-9].+?)\/b")
            )

        if not brand and title:
            try:
                brand = guess_brand_from_first_words(title)
            except:
                brand = guess_brand_from_first_words(title[0])
            if brand:
                brand = [brand]

        if isinstance(brand, list):
            brand = [br.strip() for br in brand if brand and 'search result' not in br.lower()]

        brand = brand or [' ']

        while isinstance(brand, (list, tuple)):
            if brand:
                brand = brand[0]
            else:
                brand = None
                break

        # remove authors
        if response.xpath('//*[contains(@id, "byline")]//*[contains(@class, "author")]'):
            brand = None

        if isinstance(brand, (str, unicode)):
            brand = brand.strip()

        if brand:
            brand = find_brand(brand)

        return brand

    def _parse_model(self, response, add_xpath=None):

        try:
            model = None
            if response.xpath('//th[contains(text(), "Item model number")]'
                                   '/following-sibling::td/text()'):
                model = response.xpath('//th[contains(text(), "Item model number")]'
                                       '/following-sibling::td/text()')[0].extract().strip()
            if response.xpath('//b[contains(text(), "Item model number")]'
                                       '/following-sibling::text()'):
                model = response.xpath('//b[contains(text(), "Item model number")]'
                                       '/following-sibling::text()')[0].extract().strip()

            return model

        except:
            return " "

    def _parse_price(self, response, add_xpath=None):
        """
        Parses product price.
        :param add_xpath: Additional xpathes, so you don't need to change base class
        """
        xpathes = '//b[@class="priceLarge"]/text()[normalize-space()] |' \
                  '//div[contains(@data-reftag,"atv_dp_bb_est_hd_movie")]' \
                  '/button/text()[normalize-space()] |' \
                  '//span[@id="priceblock_saleprice"]/text()[normalize-space()] |' \
                  '//div[@id="mocaBBRegularPrice"]/div/text()[normalize-space()] |' \
                  '//*[@id="priceblock_ourprice"][contains(@class, "a-color-price")]' \
                  '/text()[normalize-space()] |' \
                  '//*[@id="priceBlock"]/.//span[@class="priceLarge"]' \
                  '/text()[normalize-space()] |' \
                  '//*[@id="actualPriceValue"]/*[@class="priceLarge"]' \
                  '/text()[normalize-space()] |' \
                  '//*[@id="actualPriceValue"]/text()[normalize-space()] |' \
                  '//*[@id="buyNewSection"]/.//*[contains(@class, "offer-price")]' \
                  '/text()[normalize-space()] |' \
                  '//div[contains(@class, "a-box")]/div[@class="a-row"]' \
                  '/text()[normalize-space()] |' \
                  '//span[@id="priceblock_dealprice"]/text()[normalize-space()] |' \
                  '//*[contains(@class, "price3P")]/text()[normalize-space()] |' \
                  '//span[@id="ags_price_local"]/text()[normalize-space()] |' \
                  '//div[@id="olpDivId"]/.//span[@class="price"]' \
                  '/text()[normalize-space()] |' \
                  '//div[@id="buybox"]/.//span[@class="a-color-price"]' \
                  '/text()[normalize-space()] |' \
                  '//div[@id="unqualifiedBuyBox"]/.//span[@class="a-color-price"]/text() |' \
                  '//div[@id="tmmSwatches"]/.//li[contains(@class,"selected")]/./' \
                  '/span[@class="a-color-price"] |' \
                  '//div[contains(@data-reftag,"atv_dp_bb_est_sd_movie")]/button/text() |' \
                  '//span[contains(@class, "header-price")]/text()'

        if add_xpath:
            xpathes += ' |' + add_xpath

        price_currency_view = getattr(self, 'price_currency_view', None)
        price_currency = getattr(self, 'price_currency', None)

        if not price_currency and not price_currency_view:
            self.log('Either price_currency or price_currency_view '
                     'is not defined. Or both.', ERROR)
            return None

        price_currency_view = unicode(self.price_currency_view)
        price = response.xpath(xpathes).extract()
        if price:
            price = price[0].strip()
        # extract 'used' price only if there is no 'normal' price, because order of xpathes
        # may be undefined (in document order)
        if not price:
            price = response.xpath(
                '//div[@id="usedBuySection"]//span[contains(@class, "a-color-price")]/text()'
            ).extract()

        if not price:
            price = response.xpath('//span[@class="guild_priceblock_value a-hidden"]//text()').extract()
            if price:
                price = price[0].strip()
        # TODO fix properly
        if not price:
            price = response.xpath(
                './/*[contains(text(), "Used & new")]/../text()'
            ).extract()
            if price:
                price = [price[0].split('from')[-1]]
        if price:
            price = re.findall('\d+', price)
        return price[0] if price else " "

    def _parse_price_original(self, response, add_xpath=None):
        """
        Parses product's original price.
        :param add_xpath: Additional xpathes, so you don't need to change base class
        """
        xpathes = '//*[@id="price"]/.//*[contains(@class, "a-text-strike")]' \
                  '/text()'

        if add_xpath:
            xpathes += ' |' + add_xpath

        price_original = response.xpath(xpathes).re(FLOATING_POINT_RGEX)
        if price_original:
            return float(price_original[0].replace(',', ''))

    def _parse_description(self, response, add_xpath=None):
        """
        Parses product description.
        :param add_xpath: Additional xpathes, so you don't need to change base class
        """

        description_str = " "

        xpathes = '//*[contains(@class, "productDescriptionWrapper")]//text() |' \
                  '//div[@id="descriptionAndDetails"]//text() |' \
                  '//div[@id="feature-bullets"]//text() |' \
                  '//div[@id="ps-content"]//text() |' \
                  '//div[@id="productDescription_feature_div"]//text() |' \
                  '//div[contains(@class, "dv-simple-synopsis")]//text() |' \
                  '//div[@class="bucket"]/div[@class="content"]//text() |' \
                  '//div[@id="bookDescription_feature_div"]/noscript//text()'

        if add_xpath:
            xpathes += ' |' + add_xpath

        description = response.xpath(xpathes).extract()
        if description:
            for des in description:
                if 'jQuery' in des:
                    des = " "
                if '{' in des:
                    des = " "
                description_str = description_str + " " + des.strip()
        return description_str if description_str else None


    @staticmethod
    def _parse_asin(response):
        asin = response.xpath(
            './/*[contains(text(), "ASIN")]/following-sibling::td/text()|.//*[contains(text(), "ASIN")]'
            '/following-sibling::text()[1]').extract()
        asin = [a.strip() for a in asin if a.strip()]
        asin = asin[0] if asin else None
        if not asin:
            asin = re.search('dp/([A-Z\d]+)', response.url)
            asin = asin.group(1) if asin else None

        if asin == 'Would you like to':
            asin = re.search('dp/([A-Z\d]+)', response.url)
            asin = asin.group(1) if asin else None

        return asin

    def _parse_variants(self, response):
        """
        Parses product variants.
        """
        av = AmazonVariants()
        av.setupSC(response, response.url)
        variants = av._variants()

        return variants

    def _parse_swatches(self, response):
        """
        Parses product variants.
        """
        av = AmazonVariants()
        av.setupSC(response, response.url)
        swatches = av._swatches()

        return swatches

    def send_next_request(self, reqs, response):
        """
        Helps to handle several requests
        """
        req = reqs.pop(0)
        new_meta = response.meta.copy()

        if reqs:
            new_meta["reqs"] = reqs

        return req.replace(meta=new_meta)

    # Captcha handling functions.
    def _has_captcha(self, response):
        is_captcha = response.xpath('.//*[contains(text(), "Enter the characters you see below")]')
        # DEBUG
        # is_captcha = True
        if is_captcha:
            # This may turn on crawlera for all requests
            # self.log("Detected captcha, turning on crawlera for all requests", level=WARNING)
            # self.dont_proxy = False
            self.log("Detected captcha, using captchabreaker", level=WARNING)
            return True
        return False

    def _solve_captcha(self, response):
        forms = response.xpath('//form')
        assert len(forms) == 1, "More than one form found."

        captcha_img = forms[0].xpath(
            '//img[contains(@src, "/captcha/")]/@src').extract()[0]

        self.log("Extracted captcha url: %s" % captcha_img, level=DEBUG)
        return self._cbw.solve_captcha(captcha_img)

    def _handle_captcha(self, response, callback):
        # import pdb; pdb.set_trace()
        # FIXME This is untested and wrong.
        captcha_solve_try = response.meta.get('captcha_solve_try', 0)
        url = response.url

        self.log("Captcha challenge for %s (try %d)."
                 % (url, captcha_solve_try),
                 level=INFO)

        captcha = self._solve_captcha(response)
        if captcha is None:
            self.log(
                "Failed to guess captcha for '%s' (try: %d)." % (
                    url, captcha_solve_try),
                level=ERROR
            )
            result = None
        else:
            self.log(
                "On try %d, submitting captcha '%s' for '%s'." % (
                    captcha_solve_try, captcha, url),
                level=INFO
            )

            meta = response.meta.copy()
            meta['captcha_solve_try'] = captcha_solve_try + 1
            result = FormRequest.from_response(
                response,
                formname='',
                formdata={'field-keywords': captcha},
                callback=callback,
                dont_filter=True,
                meta=meta)

        return result

    def exit_point(self, product, next_req):
        if next_req:
            next_req.replace(meta={"product": product})
            return next_req
        return product

    def _marketplace_seller_name_parse(self, name):
        if not name:
            return name

        if ' by ' in name:  # most likely it's ' and Fulfilled by' remains
            name = name.split('and Fulfilled', 1)[0].strip()
            name = name.split('and fulfilled', 1)[0].strip()
            name = name.split('Dispatched from', 1)[0].strip()
            name = name.split('Gift-wrap', 1)[0].strip()
        if ' by ' in name:
            self.log('Multiple "by" occurrences found', WARNING)
        if 'Inc. ' in name:
            name = name.split(', Inc.', 1)[0] + ', Inc.'
        if 'Guarantee Delivery' in name:
            name = name.split('Guarantee Delivery', 1)[0].strip()
        if 'Deals in' in name:
            name = name.split('Deals in', 1)[0].strip()
        if 'Choose' in name:
            name = name.split('Choose', 1)[0].strip()
        if 'tax' in name:
            name = name.split('tax', 1)[0].strip()
        if 'in easy-to-open' in name:
            name = name.split('in easy-to-open', 1)[0].strip()
        if 'easy-to-open' in name:
            name = name.split('easy-to-open', 1)[0].strip()
        if '(' in name:
            name = name.split('(', 1)[0].strip()
        if 'exclusively for Prime members' in name:
            name = name.split('exclusively for Prime members', 1)[0].strip()
        if name.endswith('.'):
            name = name[0:-1]
        return name

    def _parse_marketplace_from_top_block(self, response):
        """ Parses "top block" marketplace ("Sold by ...") """
        top_block = response.xpath('//*[contains(@id, "sns-availability")]'
                                   '//*[contains(text(), "old by")]')
        if not top_block:
            top_block = response.xpath('//*[contains(@id, "merchant-info")]'
                                       '[contains(text(), "old by")]')
        if not top_block:
            return

        seller_id = re.search(r'seller=([a-zA-Z0-9]+)">', top_block.extract()[0])
        if not seller_id:
            seller_id = re.search(r'seller=([a-zA-Z0-9]+)&', top_block.extract()[0])
        if seller_id:
            seller_id = seller_id.group(1)

        sold_by_str = ''.join(top_block.xpath('.//text()').extract()).strip()
        sold_by_str = sold_by_str.replace('.com.', '.com').replace('\t', '') \
            .replace('\n', '').replace('Gift-wrap available', '').replace(' .', '').strip()
        sold_by_whom = sold_by_str.split('by', 1)[1].strip()
        sold_by_whom = self._marketplace_seller_name_parse(sold_by_whom)
        if not sold_by_whom:
            self.log('Invalid "sold by whom" at %s' % response.url, ERROR)
            return
        product = response.meta['product']
        _marketplace = product.get('marketplace', [])
        _price = product.get('price', None)
        _currency = None
        _price_decimal = None
        if _price is not None:
            _price_decimal = float(_price.price)
            _currency = _price.priceCurrency
        _marketplace.append({
            'currency': _currency or self.price_currency,
            'price': _price_decimal if _price else None,
            'name': sold_by_whom,
            'seller_id': seller_id if seller_id else None,
            'condition': 'new'
        })
        product['marketplace'] = _marketplace
        return product

    def _check_buybox_owner(self, response):
        buybox = "".join([x.strip() for x in response.xpath('//*[contains(@id, "merchant-info")]//text()').extract()])
        if buybox:
            return True
        else:
            buybox = "".join(
                [x.strip() for x in response.xpath('//div[@id="pantry-availability-brief"]/text()').extract()])
            if not buybox:
                return False
            else:
                return 'sold by' in buybox.lower() or 'ships from' in buybox.lower()

    def _parse_cart_data(self, response):
        reqs = response.meta.get('reqs')
        product = response.meta.get('product')
        all_price_values = response.xpath(
            '//span[@class="a-color-price hlb-price a-inline-block a-text-bold"]/text()'
        ).re(FLOATING_POINT_RGEX)
        if all_price_values:
            price_value = all_price_values[0]
            product['price'] = Price(self.price_currency, price_value)
            marketplace = product.get('marketplace')
            if marketplace:
                marketplace[0]['price'] = price_value

        if reqs:
            return self.send_next_request(reqs, response)

    @staticmethod
    def _strip_currency_from_price(val):
        return val.strip().replace('$', '').replace('£', '') \
            .replace('CDN', '').replace(u'\uffe5', '').replace('EUR', '') \
            .replace(',', '.').strip()

    @staticmethod
    def _replace_duplicated_seps(price):
        """ 1.264.67 --> # 1264.67, 1,264,67 --> # 1264,67 """
        if '.' in price:
            sep = '.'
        elif ',' in price:
            sep = ','
        else:
            return price
        left_part, reminder = price.rsplit(sep, 1)
        return left_part.replace(sep, '') + '.' + reminder

    @staticmethod
    def _fix_dots_commas(price):
        if '.' and ',' in price:
            dot_index = price.find('.')
            comma_index = price.find(',')
            if dot_index < comma_index:  # 1.264,67
                price = price.replace('.', '')
            else:  # 1,264.45
                price = price.replace(',', '')
        if price.count('.') >= 2 or price.count(',') >= 2:  # something's wrong - # 1.264.67
            price = AmazonBaseClass._replace_duplicated_seps(price)
        return price

    def _get_marketplace_price_from_cart(self, response, marketplace_block):
        data_modal = {}
        try:
            data_modal = json.loads(marketplace_block.xpath(
                '//*[contains(@data-a-modal, "hlc")]/@data-a-modal'
            ).extract()[0])
        except Exception as e:
            self.log('Error while parsing JSON modal data %s at %s' % (
                str(e), response.url), ERROR)
        get_price_url = data_modal.get('url', None)
        if get_price_url.startswith('/') and not get_price_url.startswith('//'):
            domain = urlparse.urlparse(response.url).netloc
            get_price_url = urlparse.urljoin('http://' + domain, get_price_url)
        if get_price_url:
            self.log('Getting "cart" seller price at %s for %s' % (
                response.url, get_price_url))
            seller_price_cont = requests.get(
                get_price_url,
                headers={'User-Agent': random.choice(self.MKTP_USER_AGENTS)}
            ).text
            lxml_doc = lxml.html.fromstring(seller_price_cont)
            seller_price = lxml_doc.xpath(
                '//*[contains(@id, "priceblock_ourprice")]//text()')
            if seller_price:
                _price = ' '.join([p.strip() for p in seller_price])
                _price = re.search(r' .{0,2}([\d\.,]+) ', _price)
                if _price:
                    return [_price.group(1)]

    def _parse_marketplace_from_static_right_block_more(self, response):
        product = response.meta['product']
        reqs = response.meta.get('reqs')

        _prod_price = product.get('price', [])
        _prod_price_currency = None
        if _prod_price:
            _prod_price_currency = _prod_price.priceCurrency

        _marketplace = product.get('marketplace', [])
        for seller_row in response.xpath('//*[@id="olpOfferList"]//div[contains(@class,"olpOffer")]'):
            _name = seller_row.xpath('div[4]//h3//a/text()|div[4]//@alt').extract()
            _price = seller_row.xpath('div[1]//*[contains(@class,"olpOfferPrice")]/text()').extract()
            _price = float(self._strip_currency_from_price(
                self._fix_dots_commas(_price[0].strip()))) if _price else None

            _seller_id = seller_row.xpath('div[4]//h3//a/@href').re('seller=(.*)\&?') or seller_row.xpath(
                'div[4]//h3//a/@href').re('shops/(.*?)/')
            _seller_id = _seller_id[0] if _seller_id else None

            _condition = seller_row.xpath('div[2]//*[contains(@class,"olpCondition")]/text()').extract()
            _condition = self._clean_condition(_condition[0]) if _condition else None

            if _name and not any(_seller_id and m.get('seller_id') == _seller_id for m in _marketplace):
                _name = self._marketplace_seller_name_parse(_name[0])
                _marketplace.append({
                    'name': _name.replace('\n', '').strip(),
                    'price': _price,
                    'currency': _prod_price_currency or self.price_currency,
                    'seller_id': _seller_id,
                    'condition': _condition
                })
        if _marketplace:
            product['marketplace'] = _marketplace
        else:
            product['marketplace'] = []

        next_page = response.xpath('//*[@class="a-pagination"]/li[@class="a-last"]/a/@href').extract()
        meta = response.meta
        if next_page:
            return Request(
                url=urlparse.urljoin(response.url, next_page[0]),
                callback=self._parse_marketplace_from_static_right_block_more,
                meta=meta,
                dont_filter=True
            )

        elif reqs:
            return self.send_next_request(reqs, response)

        return product

    @staticmethod
    def _clean_condition(condition):
        return re.sub(r'[\s]+', ' ', condition).lower().strip()

    def _parse_marketplace_from_static_right_block(self, response):
        # try to collect marketplaces from the main page first, before sending extra requests
        product = response.meta['product']

        others_sellers = response.xpath('//*[@id="mbc"]//a[contains(@href, "offer-listing")]/@href').extract()
        if not others_sellers:
            others_sellers = response.xpath('//a[@title="See All Buying Options"]/@href').extract()
        if not others_sellers:
            others_sellers = response.xpath('//span[@id="availability"]/a/@href').extract()
        if not others_sellers:
            others_sellers = response.xpath('//div[@id="availability"]/span/a/@href').extract()
        if others_sellers:
            meta = response.meta
            url = urlparse.urljoin(response.url, others_sellers[0])
            if is_valid_url(url):
                return product, Request(url=url,
                                        callback=self._parse_marketplace_from_static_right_block_more,
                                        meta=meta,
                                        dont_filter=True,
                                        )

        _prod_price = product.get('price', [])
        _prod_price_currency = None
        if _prod_price:
            _prod_price_currency = _prod_price.priceCurrency

        _marketplace = product.get('marketplace', [])
        for mbc_row in response.xpath('//*[@id="mbc"]//*[contains(@class, "mbc-offer-row")]'):
            _price = mbc_row.xpath('.//*[contains(@class, "a-color-price")]/text()').extract()
            _name = mbc_row.xpath('.//*[contains(@class, "mbcMerchantName")]/text()').extract()

            _json_data = None
            try:
                _json_data = json.loads(mbc_row.xpath(
                    './/*[contains(@class, "a-declarative")]'
                    '[contains(@data-a-popover, "{")]/@data-a-popover').extract()[0])
            except Exception as e:
                self.log("Error while parsing json_data: %s at %s" % (
                    str(e), response.url), ERROR)
            merchant_id = None
            if _json_data:
                merchant_url = _json_data.get('url', '')
                merchant_id = re.search(r'&me=([A-Za-z\d]{3,30})&', merchant_url)
                if merchant_id:
                    merchant_id = merchant_id.group(1)

            if not _price:  # maybe price for this seller available only "in cart"
                _price = self._get_marketplace_price_from_cart(response, mbc_row)

            _price = float(self._strip_currency_from_price(
                self._fix_dots_commas(_price[0]))) \
                if _price else None

            if _name:
                _name = self._marketplace_seller_name_parse(_name[0])
                # handle values like 1.264,67
                _marketplace.append({
                    'name': _name.replace('\n', '').strip(),
                    'price': _price,
                    'currency': _prod_price_currency or self.price_currency,
                    'seller_id': merchant_id
                })

        product['marketplace'] = _marketplace
        return product, None

    @staticmethod
    def _extract_parent_asin(response):
        parent_asin = response.xpath(
            '//span[@id="twisterNonJsData"]/input[@type="hidden" and @name="ASIN"]/@value'
        ).extract()
        return parent_asin[0] if parent_asin else None

    @staticmethod
    def _is_prime_pantry_product(response):
        return bool(
            response.xpath(
                '//select[@class="nav-search-dropdown searchSelect"]'
                '/option[@selected="selected" and contains(., "Prime Pantry")]'
            )
        )

    @staticmethod
    def _build_prime_pantry_zip_request(request, zip_code):
        scheme, netloc, url, params, query, fragment = urlparse.urlparse(request.url)
        query = 'zip={}'.format(zip_code)
        url = urlparse.urlunparse((scheme, netloc, url, params, query, fragment))
        request.meta['is_prime_pantry_zip_code'] = True
        return request.replace(
            url=url,
            cookies={'x-main': 'DCAc9NunctxhDnXRrzgxMP76tveuHIn5'}
        )
