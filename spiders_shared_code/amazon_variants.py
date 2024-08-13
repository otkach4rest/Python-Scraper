# ~~coding=utf-8~~
from __future__ import division, absolute_import, unicode_literals
import json
import collections
import ast
import itertools
import re
import lxml.html
import requests
import itertools
from scrapy import Request



class AmazonVariants(object):

    def setupSC(self, response, product_url=None):
        """ Call it from SC spiders """
        self.CH_price_flag = True
        self.response = response
        self.tree_html = lxml.html.fromstring(response.body)
        self.product_url = product_url

    def setupCH(self, tree_html, product_url=None):
        """ Call it from CH spiders """
        self.CH_price_flag = True
        self.tree_html = tree_html
        self.product_url = product_url

    def _find_between(self, s, first, last, offset=0):
        try:
            start = s.index(first, offset) + len(first)
            end = s.index(last, start)
            return s[start:end]
        except ValueError:
            return ""

    def _swatches(self):
        try:
            swatch_image_json = json.loads(re.search("obj\s=\sjQuery.parseJSON\('(.*?)'\);",
                                                     lxml.html.tostring(self.tree_html)).group(1),
                                           object_pairs_hook=collections.OrderedDict)
        except Exception as e:
            print e
            swatch_image_json = {}

        swatch_list = swatch_image_json.get('colorImages', {})

        return swatch_list

    def _variants(self):
        variants = []
        try:
            canonical_link = self.tree_html.xpath("//link[@rel='canonical']/@href")
            original_product_canonical_link = canonical_link[0] if canonical_link else None
            variants_json_data = self.tree_html.xpath('''.//script[contains(text(), "P.register('twister-js-init-dpx-data")]/text()''')[0]
            variants_json_data = re.findall('var\s?dataToReturn\s?=\s?({.+});', variants_json_data, re.DOTALL)
            cleared_vardata = variants_json_data[0].replace("\n", "")
            cleared_vardata = re.sub("\s\s+", "", cleared_vardata)
            cleared_vardata = cleared_vardata.replace(',]', ']').replace(',}', '}')
            variants_data = json.loads(cleared_vardata)
            all_variations_array = variants_data.get("dimensionValuesData", [])
            all_combos = list(itertools.product(*all_variations_array))
            all_combos = [list(a) for a in all_combos]
            asin_combo_dict = variants_data.get("dimensionValuesDisplayData", {})
            props_names = variants_data.get("dimensionsDisplay", [])
            instock_combos = []
            all_asins = []
            # Fill instock variants
            for asin, combo in asin_combo_dict.items():
                all_asins.append(asin)
                instock_combos.append(combo)
                variant = {}
                variant["asin"] = asin
                properties = {}
                for index, prop_name in enumerate(props_names):
                    properties[prop_name] = combo[index]
                variant["properties"] = properties
                variant["in_stock"] = True
                variants.append(variant)
                if original_product_canonical_link:
                    variant["url"] = "/".join(original_product_canonical_link.split("/")[:-1]) + "/{}".format(asin)
                else:
                    variant["url"] = "/".join(self.product_url.split("/")[:-1]) + "/{}".format(asin)
            # Get prices for in_stoc variants
            # Only for CH, for SC price extraction done on sc scraper side
            if self.CH_price_flag:
                v_price_map = self._get_CH_variants_price_v2(all_asins)
                for variant in variants:
                    var_asin = variant.get("asin")
                    price = v_price_map.get(var_asin)
                    if price:
                        price = (price[:-3] + price[-3:].replace(',', '.')).replace(',', '')
                        price = round(float(price[1:]), 2)
                        variant["price"] = price

                # Fill OOS variants
            oos_combos = [c for c in all_combos if c not in instock_combos]
            for combo in oos_combos:
                variant = {}
                properties = {}
                for index, prop_name in enumerate(props_names):
                    properties[prop_name] = combo[index]
                variant["properties"] = properties
                variant["in_stock"] = False
                variants.append(variant)
            # Price for variants is extracted on SC - scraper side, maybe rework it here as well?
        except Exception as e:
            print 'Error extracting v2 variants:', e

        return variants

    def _get_CH_variants_price_v2(self, all_asins):
        # Break asins into chunks of 20
        v_asin_chunks = [all_asins[i:i + 20] for i in xrange(0, len(all_asins), 20)]

        v_price_map = {}

        try:
            referer = self.product_url.split('?')[0]
            parent_asin = self.tree_html.xpath('//input[@type="hidden" and @name="ASIN"]/@value')[0]
            group_id = re.search('productGroupId=(\w+)', lxml.html.tostring(self.tree_html)).group(1)
            store_id = self.tree_html.xpath('//input[@id="storeID" and @name="storeID"]/@value')[0]

            # Get variant price info
            for chunk in v_asin_chunks:
                asins = ','.join(chunk)

                url = "https://www.amazon.com/gp/twister/dimension?asinList={a}" \
                      "&productGroupId={g}" \
                      "&storeId={s}" \
                      "&parentAsin={p}".format(a=asins, g=group_id, s=store_id, p=parent_asin)

                headers = {'Referer': referer}

                # TODO: do not use requests
                v_price_json = json.loads(requests.get(url, headers=headers, timeout=10).content)
                for v in v_price_json:
                    v_price_map[v['asin']] = v['price']
        except Exception as e:
            print 'Error extracting variant prices v2:', e
        return v_price_map
