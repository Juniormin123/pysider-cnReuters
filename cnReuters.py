#coding: utf-8


import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode
import threading
from queue import Queue, Empty
#import json
import os
import sys
import time
import logging


# typing
_L = type(logging.Logger)
_R = type(requests.Request)
_REP = type(requests.Response)
_S = type(requests.Session)
_Q = type(Queue)
#_LOC = type(threading.local())


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
def check_path(target_path:str, logger:_L)->None:
    paths = os.listdir()
    if target_path in paths:
        logger.debug(f'path "{target_path}" already exists')
    else:
        os.mkdir(target_path)
        logger.debug(f'path "{target_path}" created')


#
# requests related functions
#
def create_request(start:int, offset:int, headers:dict)->list:
    req_list = []
    for i in range(start, start+offset+1):
        param = PARAMS
        param['page'] = i
        url = BASE_URL + urlencode(param)
        req_list.append(
            requests.Request('GET', url=url, headers=headers)
        )
    return req_list


def get_request(request:_R, page_count:int, session:_S, logger:_L)->_REP:
    """use session to get request from a prepared Request object"""
    prep = session.prepare_request(request)
    try:
        t1 = time.time()
        resp = session.send(prep)
        #resp = session.get(request)
        #resp = requests.get(request)
        t2 = time.time()
        logger.info(f'[{resp.status_code}] page '
                    f'{page_count!s} done, {t2-t1:.5f}s')
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

    def __init__(self, titles:list=None, contents:list=None, dates:list=None):
        self._data = dict()
        if all((titles, contents, dates)):
            self.set_titles_contents(titles, contents, dates)
        self.count = type(self)._count
        type(self)._count += 1
    
    @classmethod
    def reset_page_count(cls, initial:int=0):
        cls._count = initial
    
    def set_titles_contents(self, titles:list, contents:list, dates:list)->None:
        for i, (t, c, d) in enumerate(zip(titles, contents, dates)):
            self._data[f'article_{i}'] = dict(title=t, content=c, date=d)
    
    def items(self):
        return self._data.items()
    
    def __getitem__(self, index:int):
        if index < 0 or index > len(self._data):
            raise IndexError(f'index {index} out of range')
        else:
            return self._data[f'article_{index}']
    
    def __len__(self):
        return len(self._data)
    
    def __str__(self):
        name = type(self).__name__
        return f'{name}_{self.count}(content_count={len(self)})'


#
# process response
#
def parse_response(response:_REP, page:Page, logger:_L)->Page:
    """extract title and content from a response, using bs4"""
    try:
        text = response.text
        if text:
            html = BeautifulSoup(text, 'lxml')
        else:
            logger.error('empty response, skip')
            return
        articles = html.select('div.news-headline-list article')
        # some text may have \n, \s, \t at the beginning, use strip() to delete
        titles = [tag.select('h3.story-title')[0].text.strip()
                  for tag in articles]
        contents = [tag.select('div.story-content p')[0].text.strip()
                    for tag in articles]
        dates = [tag.select('span.timestamp')[0].text.strip()
                 for tag in articles]
        # will not generate a Page object here, use the pre-generate one to
        # preseve the page order
        page.set_titles_contents(titles, contents, dates)
        logger.debug(f'response processed for {page}')
        return page
    except Exception as e:
        logger.exception(f'"{e}", skip to next response')


#
# output to file
#
def output(target_path:str, pages:list, logger:_L, file_name:str=None)->None:
    cwd = os.getcwd()
    if not file_name:
        today = time.strftime("%Y%m%d_%H_%M_%S")
        file_name = os.path.join(cwd, target_path, today)+'.txt'
    else:
        file_name = os.path.join(cwd, target_path, file_name)
    with open(file_name, 'a+', encoding='utf-8') as file:
        try:
            for page in pages:
                try:
                    file.write(f'Page {page.count}\n')
                    for index, article in page.items():
                        file.write(f'{index}\n')
                        file.write(f'Datetime: {article["date"]}\n')
                        file.write(f'{article["title"]}\n')
                        file.write(f'{article["content"]}\n')
                        file.write('\n')
                except KeyError as e:
                    logger.error(f'no key "{e}" for page {page}, '
                                 f'skip to next article for {page}')
            logger.info(f'output to file {file_name} complete')
        except Exception as e:
            logger.exception(e)
            

#
# threading related
#
def worker_downloader(order:int, task_q:_Q, output_q:_Q, logger:_L)->None:
    logger.warning(f'downloader {order} starts')
    session = requests.Session()
    while not task_q.empty():
        try:
            request, page = task_q.get(timeout=0.5)
            resp = get_request(request, page.count, session, logger)
            output_q.put((resp, page))
        except Empty:
            pass
        # test
        #time.sleep(5)
    logger.warning(f'task queue empty, downloader {order} stopped')


def worker_parser(order:int, output_q:_Q, result_q:_Q, logger:_L)->None:
    logger.warning(f'parser {order} starts')
    while True:
        try:
            resp, page = output_q.get(timeout=0.5)
            if (resp, page) == ('DONE', 'DONE'):
                output_q.put((resp, page))
                break
            page = parse_response(resp, page, logger)
            result_q.put(page)
        except Empty:
            pass
    logger.warning(f'Signal received, parser {order} stopped')


def signal_parser(output_q:_Q, downloader_th_list:list, logger:_L)->None:
    """
    iterate through the parser thread list, if all downloader thread stopped,
    send X number of signals, X is decided by the count of parser threads
    """
    while True:
        empty = output_q.empty()
        if all([not th.is_alive() for th in downloader_th_list]) and empty:
            break
    logger.debug('all downloader threads stopped; output queue empty')
    for i in range(len(downloader_th_list)):
        output_q.put(('DONE', 'DONE'))
    logger.debug('SIGNAL sent for parser threads')


def gather_results(result_q:_Q, logger:_L=None)->list:
    logger.debug('gathering results')
    results = []
    while True:
        try:
            results.append(result_q.get(timeout=0.5))
        except Empty:
            break
    # sort the page to maintain order in the output file
    results.sort(key=lambda page: page.count)
    # test
    #print(f'result_len={len(results)}')
    return results


#
# main
#
def main(target_path:str, file_name:str, logger:_L, 
         start:int, offset:int, headers:dict=HEADERS,
         downloader_count:int=6, parser_count:int=2)->None:
    t1 = time.time()
    task_q, output_q, result_q = Queue(), Queue(), Queue()
    # assign task lists
    req_list = create_request(start, offset, headers)
    #print(req_list)
    Page.reset_page_count(start)
    for req in req_list:
        task_q.put((req, Page()))
    # create downloader threads
    #local = threading.local()
    downloader_th_list = []
    for i in range(downloader_count):
        downloader_th_list.append(
            threading.Thread(
                target=worker_downloader, args=(
                    i, task_q, output_q, logger)
            )
        )
    # create parser threads
    parser_th_list = []
    for i in range(parser_count):
        parser_th_list.append(
            threading.Thread(
                target=worker_parser, args=(i, output_q, result_q, logger)
            )
        )
    
    th_list = downloader_th_list + parser_th_list
    for th in th_list:
        th.start()
    # do not join parser threads, as their stop signal is sent below
    # otherwise deadlock here
    for th in downloader_th_list:
        th.join()
    
    # send signal to stop parser thread;
    # do not send signal inside the downloader threads, as one downloader may
    # send the signal earlier than other downloaders which will send Page
    # result, causing some Page object missing from result list
    signal_parser(output_q, downloader_th_list, logger)

    # gather results for output to a file
    pages = gather_results(result_q, logger)

    # output to file
    output(target_path, pages, logger)

    logger.warning(f'MainThread stopped, total time: {time.time()-t1:.5f}s')


if __name__ == '__main__':
    import argparse
    arg_parser = argparse.ArgumentParser(
        description='A multi-thread web crawler for cn Reuters\' news summary.'
    )
    arg_parser.add_argument(
        '-s', '--start', type=int, default=1, 
        help='starting page to crawl, an positive integer'
    )
    arg_parser.add_argument(
        '-o', '--offset', type=int, default=20,
        help='define how many pages starting from the "start" '
             'page will be crwaled, an positive integer'
    )
    arg_parser.add_argument(
        '-f', '--file_path', default='cnReuters_txt',
        help='define the path where you want to store the text file'
    )
    arg_parser.add_argument(
        '-n', '--file_name', default='',
        help='the file name of output text, if no name provided, will use '
             'time when the file generated as the file name'
    )
    arg_parser.add_argument(
        '--downloader_count', type=int, default=6,
        help='define the number of downloader threads'
    )
    arg_parser.add_argument(
        '--parser_count', type=int, default=2,
        help='define the number of parser threads'
    )
    arg_parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='if set, the logging level will be set to DEBUG, otherwise WARNING'
    )
    arg_parser.add_argument(
        '--single_thread', action='store_true',
        help='use only one downloader thread and one parser thread'
    )
    
    args = arg_parser.parse_args()
    if args.verbose:
        logger = get_logger(True, logging.DEBUG)
    else:
        logger = get_logger(False, logging.WARNING)
    check_path(args.file_path, logger)
    if not args.single_thread:
        main(
            args.file_path, 
            args.file_name, 
            logger, 
            args.start, 
            args.offset,
            downloader_count=args.downloader_count,
            parser_count=args.parser_count
        )
    else:
        main(
            args.file_path, 
            args.file_name, 
            logger, 
            args.start, 
            args.offset,
            downloader_count=1,
            parser_count=1
        )
