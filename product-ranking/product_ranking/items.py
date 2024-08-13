# vim:fileencoding=UTF-8

import collections
import decimal

from scrapy.item import Item, Field


RelatedProduct = collections.namedtuple("RelatedProduct", ['title', 'url'])


LimitedStock = collections.namedtuple("LimitedStock",
                                      ['is_limited',   # bool
                                       'items_left'])  # int
BuyerReviews = collections.namedtuple(
    "BuyerReviews",
    ['num_of_reviews',  # int
     'average_rating',  # float
     'rating_by_star']  # dict, {star: num_of_reviews,}, like {1: 45, 2: 234}
)

valid_currency_codes = """AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT
 BGN BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYR BZD CAD CDF CHE CHF CHW CLF
 CLP CNH CNY COP COU CRC CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD
 FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HRK HTG HUF IDR ILS INR IQD IRR
 ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LTL
 LYD MAD MDL MGA MKD MMK MNT MOP MRO MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO
 NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR
 SDG SEK SGD SHP SLL SOS SRD SSP STD SYP SZL THB TJS TMT TND TOP TRY TTD TWD
 TZS UAH UGX USD USN USS UYI UYU UZS VEF VND VUV WST XAF XAG XAU XBA XBB XBC
 XBD XCD XDR XFU XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWD
""".split(' ')
valid_currency_codes = [c.strip() for c in valid_currency_codes if c.strip()]


class Price:
    price = None
    priceCurrency = None

    def __init__(self, priceCurrency, price):
        self.priceCurrency = priceCurrency
        if self.priceCurrency not in valid_currency_codes:
            raise ValueError('Invalid currency: %s' % priceCurrency)
        # Remove comma(s) in price string if needed (i.e: '1,254.09')
        if isinstance(price, unicode):
            price = price.encode('utf8')
        price = str(price)
        price = ''.join(s for s in price if s.isdigit() or s in [',', '.'])
        self.price = decimal.Decimal(str(price).replace(',', ''))

    def __repr__(self):
        return u'%s(priceCurrency=%s, price=%s)' % (
            self.__class__.__name__,
            self.priceCurrency, format(self.price, '.2f')
        )

    def __str__(self):
        return self.__repr__()

    # "==" operator implementation
    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self.__eq__(other)


class MarketplaceSeller:

    seller = None
    other_products = None

    def __init__(self, seller, other_products):
        self.seller = seller
        self.other_products = other_products
        if not self.other_products:
            self.other_products = None

    def __repr__(self):
        return {
            'seller': self.seller,
            'other_products': self.other_products
        }

    def __str__(self):
        return self.__repr__()


def scrapy_price_serializer(value):

    if isinstance(value, Price):
        return value.__str__()
    else:
        return value


def scrapy_marketplace_serializer(value):

    def conv_or_none(val, conv):
        return conv(val) if val is not None else val

    def get(rec, key, attr, conv):
        return conv_or_none(getattr(rec.get(key), attr, None), conv)

    try:
        iter(value)
    except TypeError:
        value = [value]
    result = []

    for rec in value:
        #import pdb; pdb.set_trace()
        if isinstance(rec, Price):
            converted = {u'price': float(rec.price),
                         u'currency': unicode(rec.priceCurrency),
                         u'name': None}
        elif isinstance(rec, dict):
            if rec.get('price', None) and rec.get('currency', None):
                converted = rec
            else:
                converted = {
                    u'price': get(rec, 'price', 'price', float),
                    u'currency': get(rec, 'price', 'priceCurrency', unicode),
                    u'name': conv_or_none(rec.get('name'), unicode),
                    u'seller_type': rec.get('seller_type', None)
                }
        else:
            converted = {u'price': None, u'currency': None,
                         u'name': unicode(rec)}

        result.append(converted)
    return result


def scrapy_upc_serializer(value):

    value = unicode(value)
    if len(value) > 12 and value.startswith('0'):
        return '0' + value.lstrip('0')
    return value


class SiteProductItem(Item):

    title = Field()
    asin = Field()
    parent_asin = Field()
    part = Field()
    url = Field()

    description = Field()
    description_html = Field()
    brand = Field()
    # price = Field(serializer=scrapy_price_serializer)
    price = Field()
    color = Field()
    size = Field()
    categories = Field()
    image_urls = Field()
    availability = Field()
    images = Field()


class Site1stdibsItem(Item):
    url = Field()
    company_name = Field()
    contact_name = Field()
    contact_email = Field()
    state = Field()
    city = Field()
    zip = Field()
    phone = Field()

class EnergyconnectionsItem(Item):
    url = Field()
    title = Field()
    product_code = Field()
    price = Field()
    description = Field()
    data_sheets = Field()
    warranty = Field()
    images = Field()

class EnergyconnectionsCategoryItem(Item):
    url = Field()
    category = Field()
    subcategory = Field()

class HubspotItem(Item):
    url = Field()
    company_name = Field()
    company_url = Field()
    account_name = Field()

class FortuneItem(Item):
    url = Field()
    company_name = Field()
    account_name = Field()

class BeerItem(Item):
    url = Field()
    brewery_name = Field()
    name = Field()
    price = Field()
    style = Field()
    abv = Field()
    ibu = Field()
    description = Field()

class DiscountCoupon(Item):

    site = Field()
    search_term = Field()
    ranking = Field()
    total_matches = Field()
    results_per_page = Field()
    scraped_results_per_page = Field()
    search_term_in_title_exactly = Field()
    search_term_in_title_partial = Field()
    search_term_in_title_interleaved = Field()
    _statistics = Field()

    category = Field()
    description = Field()
    start_date = Field()
    end_date = Field()
    discount = Field()
    conditions = Field()
    promo_code = Field()


class CheckoutProductItem(Item):
    name = Field()
    id = Field()
    price = Field()
    price_on_page = Field()
    quantity = Field()
    requested_color = Field()
    requested_color_not_available = Field()
    requested_quantity_not_available = Field()
    no_longer_available = Field()
    not_found = Field()
    color = Field()
    order_subtotal = Field()
    order_total = Field()
    promo_order_subtotal = Field()
    promo_order_total = Field()
    promo_price = Field()
    promo_code = Field()
    is_promo_code_valid = Field()
    promo_invalid_message = Field()
    url = Field()


class ScreenshotItem(Item):
    url = Field()
    image = Field()
    via_proxy = Field()
    site_settings = Field()
    creation_datetime = Field()

    def __repr__(self):
        return '[image data]'
