import re

import w3lib.url


def default(url):
    return w3lib.url.canonicalize_url(url)


def amazon(url):
    if 'ppw=fresh' in url:
        url = w3lib.url.url_query_cleaner(url, parameterlist=('ppw', ))
    return w3lib.url.canonicalize_url(url)
