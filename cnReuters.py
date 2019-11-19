#coding: utf-8


import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode
import json
import os
import sys
import time
import logging


# typing
_L = type(logging.Logger)
_R = type(requests.Request)
_REP = type(requests.Response)
_S = type(requests.Session)


# utility constants
LOGGER_NAME = 'cnReuters'
LEVEL = logging.WARNING    # level above this will always be logged
MAIN_FORMAT = '[{asctime!s} {msecs:0<8.4f}][{levelname:^10}] -{threadName}-  ' \
              '{message}'
DATE_FORMAT = '%y/%m/%d %H:%M:%S'

# request related constants
PAGE_SIZE = 10
BASE_URL = 'https://cn.reuters.com/news/archive/topic-cn-top-news?'
PARAMS = {
    'view': 'page',
    'page': 1,
    'pageSize': PAGE_SIZE
}
HEADERS = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                  ' (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36'
}


# generate logger
def get_logger(on:bool, level:int, mode:str='s', file_name:str=None)->_L:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    if mode == 'f':
        if not file_name:
            file_name = 'log.txt'
        handler = logging.FileHandler(file_name)
    else:
        handler = logging.StreamHandler(stream=sys.stdout)
    fmt = logging.Formatter(fmt=MAIN_FORMAT, datefmt=DATE_FORMAT, style='{')
    handler.setFormatter(fmt)
    handler.setLevel(level)
    logger.addHandler(handler)
    if not on:
        logging.disable(LEVEL)
    return logger


# check path
def check_path(target_name:str, logger:_L)->None:
    paths = os.listdir()
    if target_name in paths:
        logger.debug(f'path "{target_name}" already exists')
    else:
        os.mkdir(target_name)
        logger.debug(f'path "{target_name}" created')


#
# requests related functions
#
def create_request(start:int, end:int, headers:dict=HEADERS)->list:
    req_list = []
    for i in range(start, end+1):
        param = PARAMS
        param['page'] = i
        url = BASE_URL + urlencode(param)
        req_list.append(
            requests.Request('GET', url=url, headers=headers)
        )
    return req_list


def get_request(request:_R, page:int, session:_S, logger:_L)->_REP:
    """use session to get request from a prepared Request object"""
    prep = session.prepare_request(request)
    try:
        t1 = time.time()
        resp = session.send(prep)
        t2 = time.time()
        logger.info(f'[{resp.status_code}] page {page!s} done, {t2-t1:.5f}s')
        return resp
    except requests.RequestException as e:
        logger.error(e)
    except Exception as e:
        logger.exception(e)


#
# Page object
#
class Page:

    _count = 0

    def __init__(self, titles:list=None, contents:list=None):
        self._data = dict()
        if titles and contents:
            self.set_titles_contents(titles, contents)
        self.count = type(self)._count
        type(self)._count += 1
    
    @classmethod
    def reset_page_count(cls):
        cls._count = 0
    
    def set_titles_contents(self, titles:list, contents:list)->None:
        for i, (t, c) in enumerate(zip(titles, contents)):
            self._data[f'article_{i}'] = dict(title=t, content=c)
    
    def __getitem__(self, index:int):
        if index < 0 or index > len(self._data):
            raise IndexError(f'index {index} out of range')
        else:
            return self._data[f'article_{index}']
    
    def __bool__(self):
        if len(self._data) > 0:
            return True
        else:
            return False


#
# process response
#
def parse_response(response:_REP, page:Page, logger:_L):
    """extract title and content from a response, using bs4"""
    text = response.text
    try:
        if text:
            html = BeautifulSoup(text, 'lxml')
        else:
            # TODO log here
            return
        articles = html.select('div.news-headline-list article')
        titles = [tag.select('h3.story-title')[0].text 
                  for tag in articles]
        contents = [tag.select('div.story-content p')[0].text
                    for tag in articles]
        page.set_titles_contents(titles, contents)
        # TODO return value
        



if __name__ == '__main__':
    # test for utility
    #logger = get_logger(False, logging.DEBUG)
    #check_path('test2', logger)

    # test for get by Request object
    s = requests.Session()
    req_list = create_request(1, 2)
    for r in req_list:
        prep = s.prepare_request(r)
        resp = s.send(prep)
        print(resp)
        print(type(resp))
