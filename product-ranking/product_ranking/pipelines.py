# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html
from __future__ import absolute_import, division, unicode_literals

import argparse
import copy
import json
import os
import random
import string
import sys
import re
import traceback
import unittest
import urlparse
import requests


import scrapy
from scrapy.pipelines.images import ImagesPipeline

import tldextract
from scrapy import Selector, signals
from scrapy.xlib.pydispatch import dispatcher
from scrapy.log import DEBUG

from .items import Price, BuyerReviews
from .validation import _get_spider_output_filename
from .utils import get_random_positive_float_number

import pymongo
import redis

import hashlib

try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

from scrapy.utils.python import to_bytes
from scrapy.http import Request
from scrapy.exceptions import DropItem

try:
    import mock
except ImportError:
    pass  # Optional import for test.

STATISTICS_ENABLED = False
STATISTICS_ERROR_MSG = None
try:
    from .statistics import report_statistics

    STATISTICS_ENABLED = True
except ImportError as e:
    STATISTICS_ERROR_MSG = str(e)

CWD = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(CWD, '..', '..', 'deploy'))


class RemoveNoneValuesFromVariantsProperties(object):

    def process_item(self, item, spider):
        try:
            variants = item.get('variants')
            if isinstance(variants, list):
                self.remove_none_values_from_properties(variants)
        except:
            spider.log(
                'Unable to remove None values: {}'.format(traceback.format_exc())
            )
        return item

    @staticmethod
    def remove_none_values_from_properties(variants):
        for variant in variants:
            all_variant_properties = variant.get('properties', {})
            for variant_property_name, variant_property_value in all_variant_properties.items():
                if variant_property_value is None:
                    del all_variant_properties[variant_property_name]


class PriceSimulator(object):

    def process_item(self, item, spider):
        if getattr(spider, 'price_simulator', None):
            price = item.get('price')
            if isinstance(price, Price):
                price.price = get_random_positive_float_number()
                item['price'] = price

        return item


class Subscriber:
    def __init__(self, name=None):
        if not name:
            self.name = str(self.__class__).split(' ')[1].split("'")[1]
        else:
            self.name = name

    def update(self, message):
        # start new Thread in here to handle any task
        print('\n\n {} got message "{}"'.format(self.name, message))


class MyMongoClient(Subscriber):

    def __init__(self, db_name, collection_name, host='localhost', is_exchange_data=False, port=27017, *args, **kwargs):
        self._c = pymongo.MongoClient(host, port)
        self.set_database(db_name)
        self.set_collection(collection_name)
        self.collection_name = collection_name
        self.db_name = db_name
        self.redis = redis.Redis(host='localhost', port=6379, db=0)
        self.is_exchange_data = is_exchange_data

    def is_duplicate_data(self, msg):
        return self.collection.find_one(msg)

    def insert(self, data):
        self.collection.insert(data, upsert=True, multi=True)

    def upsert(self, data):
        self.collection.update(data, upsert=True, multi=True)

    def insert_one(self, data):
        self.collection.insert_one(data)
        print('------table name-----')
        print(self.collection)
        print('Inserted: \n{}'.format(data))

    def insert_many(self, data):
        self.collection.insert_many(data)

    def set_collection(self, collection_name):
        self.collection = self.database[collection_name]

    def set_database(self, db_name):
        self.database = self._c[db_name]


# class MyImagesPipeline(ImagesPipeline):
#     def get_media_requests(self, item, info):
#         for image_url in item['image_urls']:
#             if 'https' in image_url:
#                 yield scrapy.Request(image_url, meta={
#                     'url': item['url']
#                 })

    # def item_completed(self, results, item, info):
    #     asin = item.get('asin')
    #     image_paths = [x['path'] for ok, x in results if ok]
    #     if not image_paths:
    #         raise DropItem("Item contains no images")
    #     for index in range(len(image_paths)):
    #         image_path = 'images/{}-{}.jpg'.format(asin, str(index + 1))
    #         image_checksum = '{}-{}'.format(asin, str(index + 1))
    #         item['images'][index]['path'] = image_path
    #         item['images'][index]['checksum'] = image_checksum
    #         item['images'][index]['url'] = 'https://images-na.ssl-images-amazon.com/' + image_path
    #
    #     return item
    #
    # def file_path(self, request, response=None, info=None):
    #     try:
    #         ## start of deprecation warning block (can be removed in the future)
    #         def _warn():
    #             from scrapy.exceptions import ScrapyDeprecationWarning
    #             import warnings
    #             warnings.warn('ImagesPipeline.image_key(url) and file_key(url) methods are deprecated, '
    #                           'please use file_path(request, response=None, info=None) instead',
    #                           category=ScrapyDeprecationWarning, stacklevel=1)
    #
    #         # check if called from image_key or file_key with url as first argument
    #         if not isinstance(request, Request):
    #             _warn()
    #             url = request
    #         else:
    #             url = request.url
    #
    #         # detect if file_key() or image_key() methods have been overridden
    #         if not hasattr(self.file_key, '_base'):
    #             _warn()
    #             return self.file_key(url)
    #         elif not hasattr(self.image_key, '_base'):
    #             _warn()
    #             return self.image_key(url)
    #         ## end of deprecation warning block
    #
    #         asin = re.search('product/(.*?)/', request.meta.get('url')).group(1)
    #         image_name = '{} -- {}'.format(asin, url.split('/')[-1].split('.jpg')[0])
    #         return 'images/%s.jpg' % (image_name)
    #
    #     except:
    #         print('uploading error!')


class MongoPipeline(object):

    def __init__(self):
        self.db_name = 'AmazonDB'
        self.collection = 'productdata'
        try:
            self.host = 'mongodb://localhost:27017/AmazonDB'
        except KeyError:
            self.host = 'localhost'
        self.db = MyMongoClient(self.db_name, collection_name=self.collection, host=self.host)

    def process_item(self, item, spider):
        try:

            asin = item.get('asin')  # String
            if asin:
                asin = str(asin).encode('utf-8')
            else:
                asin = " "
            #
            # color = item.get('color')
            # if color:
            #     color = str(color).encode('utf-8')
            # else:
            #     color = " "
            #
            # description = item.get('description')
            # if description:
            #     description = description.encode('utf-8')
            # else:
            #     description = " "
            #
            # description_html = item.get('description_html')
            # if description_html:
            #     description_html = description_html.encode('utf-8')
            # else:
            #     description_html = " "
            #
            # part = item.get('part')  # String
            # if part:
            #     part = str(part).encode('utf-8')
            # else:
            #     part = " "
            # price = item.get('price')
            # if price:
            #     price = str(price).encode('utf-8')
            # else:
            #     price = " "
            #
            # parent_asin = item.get('promotions')  # Bool
            # if parent_asin:
            #     parent_asin = str(parent_asin).encode('utf-8')
            # else:
            #     parent_asin = " "
            #
            # title = item.get('title')  # String
            # if title:
            #     title = str(title).encode('utf-8')
            # else:
            #     title = " "
            #
            # url = item.get('url')  # String
            # if url:
            #     url = str(url).encode('utf-8')
            # else:
            #     url = " "
            #
            # size = item.get('size')  # String
            # if size:
            #     size = str(size).encode('utf-8')
            # else:
            #     size = " "
            #
            # categories = item.get('categories')  # String
            # if categories:
            #     categories = str(categories).encode('utf-8')
            # else:
            #     categories = " "
            #
            # availability = item.get('availability')  # String
            # if availability:
            #     availability = str(availability).encode('utf-8')
            # else:
            #     availability = " "
            #
            # # image_urls = item.get('image_urls')
            # # if image_urls:
            # #     for image_url in image_urls:
            # #         image_urls += image_url + " , "
            # #         image_urls = str(image_urls).encode('utf-8')
            # # else:
            # #     image_urls = " "
            #
            # json_data = {
            #     'title': title,
            #     'asin': asin,
            #     'parent_asin': parent_asin,
            #     'part': part,
            #     'url': url,
            #     'description': description,
            #     'description_html': description_html,
            #     'price': price,
            #     'color': color,
            #     'size': size,
            #     # 'image_url': image_urls,
            #     'categories': categories,
            #     'availability': availability,
            # }
            #
            # if not self.db.is_duplicate_data(json_data):
            #     self.db.insert_one(json_data)
            #     print('=================================')
            #     print('==========Inserting Data===========')
            #     print('=================================')

        except Exception as e:
            print("Error %d: %s" % e.args)

        return item


class BuyerReviewsAverageRating(object):

    def process_item(self, item, spider):
        buyer_reviews = item.get('buyer_reviews')
        if isinstance(buyer_reviews, BuyerReviews) and not buyer_reviews.average_rating:
            spider.log('Calculate average_rating with BuyerReviewsAverageRating pipeline', DEBUG)
            try:
                rating_by_star = buyer_reviews.rating_by_star
                num_of_reviews = sum(rating_by_star.values())
                average_rating = self.calculate_average_rating(rating_by_star, num_of_reviews)
                buyer_reviews = BuyerReviews(num_of_reviews, average_rating, rating_by_star)
            except:
                spider.log(
                    'Can not calculate average_rating: {}'.format(traceback.format_exc())
                )
            else:
                item['buyer_reviews'] = buyer_reviews

        return item

    @staticmethod
    def calculate_average_rating(rating_by_star, num_of_reviews):
        if num_of_reviews and rating_by_star:
            average_rating = round(
                sum(int(star) * int(number) for star, number in rating_by_star.items()) / num_of_reviews, 1
            )
        else:
            average_rating = 0

        return average_rating


class LowerVariantsPropertiesNames(object):

    def process_item(self, item, spider):
        try:
            variants = item.get('variants')
            if isinstance(variants, list):
                self.lower_properties_keys_names(variants)
        except:
            spider.log(
                'Unable to lower variants keys: {}'.format(traceback.format_exc())
            )
        return item

    @staticmethod
    def lower_properties_keys_names(variants):
        for variant in variants:
            all_variant_properties = variant.get('properties', {})
            for variant_property_name, variant_property_value in all_variant_properties.items():
                if isinstance(variant_property_name, basestring) and not variant_property_name.islower():
                    all_variant_properties[
                        variant_property_name.lower()] = all_variant_properties.pop(variant_property_name)


class CheckGoogleSourceSiteFieldIsCorrectJson(object):
    def process_item(self, item, spider):
        google_source_site = item.get('google_source_site')
        if google_source_site:
            try:
                json.loads(google_source_site)
            except:
                raise DropItem("Invalid JSON format at 'google_source_site'"
                               " field at item:")
        return item


class CutFromTitleTagsAndReturnStringOnly(object):
    def process_item(self, item, spider):
        if "title" in item:
            item["title"] = self._title_without_tags(item["title"])
        return item

    @staticmethod
    def _title_without_tags(title):
        if isinstance(title, str) or isinstance(title, unicode):
            return Selector(text=title).xpath("string()").extract()[0]
        return title


class SetRankingField(object):
    """ Explicitly set "ranking" field value (needed for
        Amazon Shelf spider, temporary solution """

    def process_item(self, item, spider):
        if hasattr(spider, 'ranking_override'):
            ranking_override = getattr(spider, 'ranking_override')
            item['ranking'] = ranking_override
        return item


class SetMarketplaceSellerType(object):
    def process_item(self, item, spider):
        spider_main_domain = spider.allowed_domains[0]
        spider_main_domain = tldextract.extract(spider_main_domain).domain
        marketplaces = item.get('marketplace', {})
        # extend the marketplace dict with the seller_type (see BZ 1869)
        for marketplace in marketplaces:
            name = marketplace.get('name', '')
            if name:
                try:
                    name_domain = tldextract.extract(name).domain
                except UnicodeEncodeError:  # non-ascii name (not domain)
                    marketplace['seller_type'] = 'marketplace'
                if spider_main_domain and name_domain:
                    if spider_main_domain.lower() in name_domain.lower():
                        marketplace['seller_type'] = 'site'
                    else:
                        marketplace['seller_type'] = 'marketplace'
        return item


class AddSearchTermInTitleFields(object):
    _TRANSLATE_TABLE = string.maketrans('', '')

    @staticmethod
    def _normalize(s):
        try:
            s = str(s).translate(
                AddSearchTermInTitleFields._TRANSLATE_TABLE,
                string.punctuation
            )
        except UnicodeEncodeError:
            # Less efficient version for truly unicode strings.
            for c in string.punctuation:
                s = s.replace(c, '')
        return s.lower()

    @staticmethod
    def process_item(item, spider):
        if "is_single_result" not in item and '_shelf_urls_products' not in spider.name:
            AddSearchTermInTitleFields.add_search_term_in_title_fields(
                item, item.get('search_term', ''))

        return item

    @staticmethod
    def is_a_partial_match(title_words, words):
        return any(word in title_words for word in words)

    @staticmethod
    def add_search_term_in_title_fields(product, search_term):
        # Initialize item.
        product['search_term_in_title_exactly'] = False
        product['search_term_in_title_partial'] = False
        product['search_term_in_title_interleaved'] = False

        try:
            # Normalize data to be compared.
            title_norm = AddSearchTermInTitleFields._normalize(
                product['title'])
            title_words = title_norm.split()
            search_term_norm = AddSearchTermInTitleFields._normalize(
                search_term)
            search_term_words = search_term_norm.split()

            if search_term_norm in title_norm:
                product['search_term_in_title_exactly'] = True
            elif AddSearchTermInTitleFields._is_title_interleaved(
                    title_words, search_term_words):
                product['search_term_in_title_interleaved'] = True
            else:
                product['search_term_in_title_partial'] \
                    = AddSearchTermInTitleFields.is_a_partial_match(
                    title_words, search_term_words)
        except KeyError:
            pass

    @staticmethod
    def _is_title_interleaved(title_words, search_term_words):
        result = False

        offset = 0
        for st_word in search_term_words:
            for i, title_word in enumerate(title_words[offset:]):
                if st_word == title_word:
                    offset += i + 1
                    break  # Found one!
            else:
                break  # A search term was not in the title.
        else:
            # The whole search term was traversed so it's interleaved.
            result = True

        return result


class FilterNonPartialSearchTermInTitle(object):
    """Filters Items where the title doesn't contain any of the
     required_keywords.

     This pipeline stage will override AddSearchTermInTitleFields as if the
     required_keywords where the search_term.
     """

    @staticmethod
    def process_item(item, spider):
        title_words = AddSearchTermInTitleFields._normalize(
            item['title']
        ).split()
        required_words = spider.required_keywords.lower().split()
        if not AddSearchTermInTitleFields.is_a_partial_match(
                title_words, required_words):
            raise DropItem(
                "Does not match title partially: %s" % item['title'])

        AddSearchTermInTitleFields.add_search_term_in_title_fields(
            item, spider.required_keywords)

        return item


class AddSearchTermInTitleFieldsTest(unittest.TestCase):
    def test_exact_multi_word_match(self):
        item = dict(title="Mary has a little Pony! ",
                    search_term=" littLe pony ")

        result = AddSearchTermInTitleFields.process_item(item, None)

        assert not result['search_term_in_title_interleaved']
        assert not result['search_term_in_title_partial']
        assert result['search_term_in_title_exactly']

    def test_search_term_in_title_interleaved(self):
        item = dict(title="My Mary has a little Pony!",
                    search_term="Mary, a pony")

        result = AddSearchTermInTitleFields.process_item(item, None)

        assert result['search_term_in_title_interleaved']
        assert not result['search_term_in_title_partial']
        assert not result['search_term_in_title_exactly']


class FilterNonPartialSearchTermInTitleTest(unittest.TestCase):
    def test_when_an_item_does_not_match_partially_then_it_should_be_filtered(self):
        item = dict(title="one two three")
        spider = mock.MagicMock()
        spider.required_keywords = "none of the ones in the title"
        self.assertRaises(
            DropItem,
            FilterNonPartialSearchTermInTitle.process_item,
            item,
            spider,
        )

    def test_when_an_item_matches_partially_then_it_should_have_the_title_match_fields(self):
        item = dict(title="one two three")
        spider = mock.MagicMock()
        spider.required_keywords = "has one word in the title"
        FilterNonPartialSearchTermInTitle.process_item(item, spider)

        assert item['search_term_in_title_partial']
        assert not item['search_term_in_title_interleaved']
        assert not item['search_term_in_title_exactly']


class MergeSubItems(object):
    """ A quote: You can't have the same item being filled in parallel requests.
        You either need to make sure the item is passed along in a chain like fashion,
         with each callback returning a request for the next page of information with
          the partially filled item in meta, or you need to write a pipeline that
           will collect and group the necessary data.
    """
    _mapper = {}
    _subitem_mode = False

    def __init__(self):
        dispatcher.connect(self.spider_opened, signals.spider_opened)
        dispatcher.connect(self.spider_closed, signals.spider_closed)
        # use extra 'create_csv_output' option for debugging
        args_ = u''.join([a.decode('utf8') for a in sys.argv])
        self.create_csv_output = (u'create_csv_output' in args_
                                  or u'save_csv_output' in args_)

    @staticmethod
    def _get_output_filename(spider):
        parser = argparse.ArgumentParser()
        parser.add_argument('-o')
        args = parser.parse_known_args()
        file_path = args[0].o
        if file_path:
            return file_path
        else:
            return spider._crawler.settings.attributes['FEED_URI'].value

    @staticmethod
    def _serializer(val):
        if isinstance(val, type(MergeSubItems)):  # class
            return val.__dict__
        else:
            return str(val)

    def spider_opened(self, spider):
        pass

    def _dump_mapper_to_fname(self, fname):
        # only for JCPenney - transform variants, see BZ 9913
        with open(fname, 'w') as fh:
            for url, item in self._mapper.items():
                fh.write(json.dumps(item, default=self._serializer) + '\n')

    def _dump_output(self, spider):
        if self._subitem_mode:  # rewrite output only if we're in "subitem mode"
            output_fname = self._get_output_filename(spider)
            if output_fname:
                self._dump_mapper_to_fname(output_fname)

    def spider_closed(self, spider):
        if self._subitem_mode:  # rewrite output only if we're in "subitem mode"
            self._dump_output(spider)
            _validation_filename = _get_spider_output_filename(spider)
            self._dump_mapper_to_fname(_validation_filename)
            if self.create_csv_output and self._get_output_filename(spider):
                # create CSV file as well
                _output_file = self._get_output_filename(spider).lower().replace('.jl', '')
                try:
                    _output_csv = convert_json_to_csv(_output_file)
                    print('Created CSV output: %s.csv' % _output_csv)
                except Exception as e:
                    print('Could not create CSV output: %s' % str(e))

    def process_item(self, item, spider):
        _item = copy.deepcopy(item)
        item = copy.deepcopy(_item)
        del _item
        _subitem = item.get('_subitem', None)
        if not _subitem:
            return item  # we don't need to merge sub-items
        self._subitem_mode = True  # switch a flag if there's at least one item with "subitem mode" found
        if 'url' in item:  # sub-items: collect them and dump them on "on_close" call
            _url = item['url']
            if _url not in self._mapper:
                self._mapper[_url] = {}
            self._mapper[_url].update(item)
            del item
            if random.randint(0, 100) == 0:
                # dump output from time to time to show progress (non-empty output file)
                self._dump_output(spider)
            raise DropItem('Multiple Sub-Items found')


class CollectStatistics(object):
    """ Gathers server and spider statistics, such as RAM, HDD, CPU etc. """

    @staticmethod
    def process_item(item, spider):
        if STATISTICS_ENABLED:
            _gather_stats = False
            if getattr(spider, 'product_url', None):
                _gather_stats = True
            else:
                _gather_stats = bool(random.randint(0, 50) == 0)
            if _gather_stats:
                try:
                    item['_statistics'] = report_statistics()
                except Exception as e:
                    item['_statistics'] = str(e)
            else:
                item['_statistics'] = ''
        else:
            item['_statistics'] = STATISTICS_ERROR_MSG
        return item


class FillPriceFieldIfEmpty(object):

    def process_item(self, item, spider):
        marketplace = item.get('marketplace', [])

        new_marketplace_prices_without_none_values = filter(
            bool,
            [seller.get('price') for seller in marketplace if seller.get('condition') == 'new']
        )

        if not item.get('price') and new_marketplace_prices_without_none_values:

            is_only_marketplace_sellers = all(
                seller.get('seller_type') == 'marketplace' for seller in marketplace
            )


            if is_only_marketplace_sellers:
                price = min(new_marketplace_prices_without_none_values)

            else:
                price = new_marketplace_prices_without_none_values[0]

            try:
                spider.log('Setting price via FillPriceFieldIfEmpty middleware')
                item['price'] = Price(spider.price_currency, price)
            except:
                spider.log(
                    'Can not convert price value to float: {}'.format(traceback.format_exc())
                )

        return item


if __name__ == '__main__':
    unittest.main()
