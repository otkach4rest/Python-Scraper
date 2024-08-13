from __future__ import division, absolute_import, unicode_literals

import re
import urlparse
from lxml import html

from product_ranking.items import EnergyconnectionsItem, EnergyconnectionsCategoryItem
from product_ranking.spiders import BaseProductsSpider, cond_set_value
from product_ranking.validation import BaseValidator

class energyconnectionsSpider(BaseValidator, BaseProductsSpider):
    name = 'energyconnections_products'
    allowed_domains = ["www.energyconnections.net.au"]

    SEARCH_URL = "https://www.1stdibs.com/search/?q={search_term}"

    def _parse_single_product(self, response):
        return self.parse_product(response)

    def parse_product(self, response):
        # product = EnergyconnectionsItem()
        product_category = EnergyconnectionsCategoryItem()

        # title = self.parse_title(response)
        # cond_set_value(product, 'title', title)
        #
        # p_code = self.parse_product_code(response)
        # cond_set_value(product, 'product_code', p_code)
        #
        # price = self.parse_price(response)
        # cond_set_value(product, 'price', price)
        #
        # product_description = self.parse_description(response)
        # cond_set_value(product, 'description', product_description)
        #
        # data_sheets = self.parse_data_sheets(response)
        # cond_set_value(product, 'data_sheets', data_sheets)
        #
        # product_warranty = self.parse_product_warranty(response)
        # cond_set_value(product, 'warranty', product_warranty)
        #
        # images = self.parse_images(response)
        # cond_set_value(product, 'images', images)
        category = self.parse_category(response)
        cond_set_value(product_category, 'category', category)

        subcategory = self.parse_subcategory(response)
        cond_set_value(product_category, 'subcategory', subcategory )
        return product_category

    def parse_title(self, response):
        title = response.xpath('//h1[@class="product-title"]/text()').extract()
        return title[0] if title else None

    def parse_product_code(self, response):
        p_code = response.xpath('//h3[@class="product-code"]/text()').extract()
        if p_code:
            p_code = p_code[0].split(":")
            if len(p_code) > 1:
                p_code = p_code[1]
            else:
                p_code = None
        return p_code if p_code else None

    def parse_price(self, response):
        price = response.xpath('//span[@class="price-sales"]/text()').extract()
        return price[0] if price else None

    def parse_description(self, response):
        XPATHES = './/span//strong/text() | ' \
                  './/span/text() | ' \
                  '//p/text()'
        p_text_list = response.xpath("//div[@id='details']//p").extract()

        text = []
        for p_text in p_text_list:
            tag = html.fromstring(p_text).xpath(XPATHES)
            if tag and (not u'\xa0' in tag):
                text.append(tag[0])

        return ' '.join(text) if text else None

    def parse_data_sheets(self, response):
        data_sheet = response.xpath('//div[@id="pds"]//li[@class="product-attachment"]//a/@href').extract()
        return data_sheet[0] if data_sheet else None

    def parse_product_warranty(self, response):
        warranty = response.xpath('//div[@id="attach"]//li[@class="product-attachment"]//a/@href').extract()
        return warranty[0] if warranty else None

    def parse_images(self, response):
        images = response.xpath('//div[contains(@class, "sp-wrap")]//a/@href').extract()
        image_urls = ['http://www.energyconnections.net.au' + url for url in images if url]
        return image_urls

    def parse_categories(self, response):
        categories = response.xpath("//ul[@class='breadcrumb']//a/text()").extract()
        return categories[2:]

    def parse_category(self, response):
        categories = self.parse_categories(response)
        category = categories[0]
        return category

    def parse_subcategory(self, response):
        categories = self.parse_categories(response)
        subcategory = categories[1]
        return subcategory

    def _scrape_total_matches(self, response):
        total_match = response.xpath(
            "//*[@data-total-products]/@data-total-products").extract()

        return int(total_match[0]) if total_match else 0

    def _scrape_product_links(self, response):
        self.product_links = response.xpath("//div[@class='description']//h4//a/@href").extract()

        for item_url in self.product_links:
            yield item_url, EnergyconnectionsItem()

    def _scrape_next_results_page_link(self, response):
        if not self.product_links:
            return
        next_page_link = response.xpath("//li[@class='next']//a/@href").extract()
        if next_page_link:
            return urlparse.urljoin(response.url, next_page_link[0])

    def _clean_text(self, text):
        return re.sub("[\n\t\r]", "", text).strip()
