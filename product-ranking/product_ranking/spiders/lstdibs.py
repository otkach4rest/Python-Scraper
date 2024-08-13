from __future__ import division, absolute_import, unicode_literals

import re
import urlparse


from product_ranking.items import Site1stdibsItem
from product_ranking.spiders import BaseProductsSpider, cond_set_value
from product_ranking.validation import BaseValidator


class lstdibsProductsSpider(BaseValidator, BaseProductsSpider):
    name = 'lstdibs_products'
    allowed_domains = ["www.1stdibs.com"]

    SEARCH_URL = "https://www.1stdibs.com/search/?q={search_term}"

    def _parse_single_product(self, response):
        return self.parse_product(response)

    def parse_product(self, response):
        product = Site1stdibsItem()

        cond_set_value(product, 'company_name', 'lstdibs')
        cond_set_value(product, 'contact_name', 'lstdibs')
        cond_set_value(product, 'contact_email', 'support@lstdibs.com')
        cond_set_value(product, 'phone', '+1(877)721-3427')
        cond_set_value(product, 'zip', '10003')

        state = self._parse_state(response)
        cond_set_value(product, 'state', state)

        city = self._parse_city(response)
        cond_set_value(product, 'city', city)

        return product

    def _parse_location(self, response):
        state = None
        city = None
        location = response.xpath("//div[@class='PdpSharedDealerDetailsStats__companyInfo__489ef6b2']"
                                  "//div")[-1].xpath(".//span/text()").extract()
        if location:
            state = location[0].split(',')[1]
            city = location[0].split(',')[0].split('in ')[1]
        return state, city

    def _parse_state(self, response):
        location = self._parse_location(response)
        return location[0].strip()

    def _parse_city(self, response):
        location = self._parse_location(response)
        return location[1].strip()

    def _scrape_total_matches(self, response):
        total_match = response.xpath(
            "//*[@data-total-products]/@data-total-products").extract()

        return int(total_match[0]) if total_match else 0

    def _scrape_product_links(self, response):
        self.product_links = list(set(response.xpath("//div[@class='product-container']//a/@href").extract()))

        for item_url in self.product_links:
            yield item_url, Site1stdibsItem()

    def _scrape_next_results_page_link(self, response):
        if not self.product_links:
            return
        next_page_link = response.xpath("//li[@class='next']//a/@href").extract()
        if next_page_link:
            return urlparse.urljoin(response.url, next_page_link[0])

    def _clean_text(self, text):
        return re.sub("[\n\t\r]", "", text).strip()
