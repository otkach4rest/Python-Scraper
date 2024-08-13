# ~~coding=utf-8~~
from __future__ import division, absolute_import, unicode_literals

import re
import urlparse
import requests
import json
from scrapy.http import Request
from lxml import html

from product_ranking.items import HubspotItem
from product_ranking.spiders import BaseProductsSpider, cond_set_value
from product_ranking.validation import BaseValidator

class linkedinProductsSpider(BaseValidator, BaseProductsSpider):
    name = 'linkedin_products'
    allowed_domains = ["www.linkedin.com"]

    def _parse_single_product(self, response):
        return self.parse_product(response)

    def parse_product(self, response):
        product = HubspotItem()
        url = "https://phantombuster.com/api/v1/agent/19472/launch"
        payload = {'output': 'first-result-object',
                   'argument': {
                       'sessionCookie': 'AQEDASTK1TEFI8A2AAABZKs1QugAAAFkz0HG6FYAcBXFzXZuPZW8SHx2kVSUCAmG7SHC6LcHZ2zeZXrvTHtjIl9IJibaeZPB2-IBykGl4nJiqObZgzJ5guiJyfyh8xUqMXbZo8AU2lQA8uinmiklwdBl',
                       # 'spreadsheetUrl': 'https://docs.google.com/spreadsheets/d/1qWQ5t-pFaibQQoltH05uH0uw_t_fArpZoYTAYh4k1Gg',
                       'profileUrls': ['https://www.linkedin.com/directory/companies'],
                       'noDatabase': True
                       }
                   }
        header = {"Content-Type": "application/json",
                  "X-Phantombuster-Key-1": "A3Euzfa9rOrWOiw0pmwzWHBZO1tz2f77",
                  "content-length": "11051"}

        response = requests.post(url, data=json.dumps(payload), headers=header)
        resp = response.status_code

    def parse_companies(self, response):
        domain = response.meta['domain']
        product = response.meta['prod']
        product['company_name'] = None
        product['url'] = None
        product['company_url'] = None
        product['account_name'] = None

        account_name = response.meta['account_name']
        website = response.meta['website']

        company_name = response.xpath("//div[@class='card-body']//dd[@class='col-sm-8']/text()").extract()
        if company_name:
            if company_name[0] == '-':
                company_name = domain.split('.')[0].upper()
            else:
                company_name = company_name[0]
        else:
            company_name = domain.split('.')[0].upper()
        cond_set_value(product, 'url', website)
        cond_set_value(product, 'company_name', company_name)
        cond_set_value(product, 'company_url', domain)
        cond_set_value(product, 'account_name', account_name)

        return product

    def _extract_page_tree(self, trend_link, st):
        tree_html = None
        attr_tree_html = None
        headers = {'Upgrade-Insecure-Requests': '1',
                   'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                                 'Chrome/67.0.3396.99 Safari/537.36'
                   }
        for i in range(3):
            try:
                with requests.Session() as s:
                    response = s.get(trend_link, verify=False)
                    if response.ok:
                        content = response.text
                        tree_html = html.fromstring(content)
                    else:
                        self.ERROR_RESPONSE['failure_type'] = response.status_code

                    attr_resp = s.get(st, verify=False, headers=headers)
                    if attr_resp.ok:
                        attr_content = attr_resp.text
                        attr_tree_html = html.fromstring(attr_content)
                    else:
                        self.ERROR_RESPONSE['failure_type'] = attr_resp.status_code

            except Exception as e:
                print 'ERROR EXTRACTING PAGE TREE', trend_link, e
                attr_resp = s.get(st.replace('www.', ''), verify=False, headers=headers)
                if attr_resp.ok:
                    attr_content = attr_resp.text
                    attr_tree_html = html.fromstring(attr_content)
                else:
                    self.ERROR_RESPONSE['failure_type'] = attr_resp.status_code

            return tree_html, attr_tree_html
        self.is_timeout = True

    def _scrape_total_matches(self, response):
        total_match = response.xpath(
            "//*[@data-total-products]/@data-total-products").extract()

        return int(total_match[0]) if total_match else 0

    def _scrape_product_links(self, response):
        self.product_links = response.xpath("//div[@class='description']//h4//a/@href").extract()

        for item_url in self.product_links:
            yield item_url, HubspotItem()

    def _scrape_next_results_page_link(self, response):
        if not self.product_links:
            return
        next_page_link = response.xpath("//li[@class='next']//a/@href").extract()
        if next_page_link:
            return urlparse.urljoin(response.url, next_page_link[0])

    def _clean_text(self, text):
        return re.sub("[\n\t\r]", "", text).strip()
