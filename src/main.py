import logging
import re
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import BASE_DIR, EXPECTED_STATUS, MAIN_DOC_URL, MAIN_PEP_URL
from outputs import control_output
from utils import find_tag, get_response


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all('li',
                                              attrs={'class': 'toctree-l1'})
    results = [('Ссылка на статью', 'Заголовок', 'Редактор, Автор')]

    for section in tqdm(sections_by_python):
        version_a_tag = find_tag(section, 'a')
        version_link = urljoin(whats_new_url, version_a_tag['href'])
        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, 'lxml')
        h1 = find_tag(soup, 'h1')
        h1_text = h1.text.replace(chr(182), '')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append((version_link, h1_text, dl_text))
    return results


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    sidebar = find_tag(soup, 'div', {'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise Exception('Ничего не нашлось')
    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        version, status = a_tag.text, ''
        if text_match:
            version, status = text_match.groups()
        results.append((link, version, status))
    return results


def download(session):
    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    response = get_response(session, downloads_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    table_tag = find_tag(soup, 'table', {'class': 'docutils'})
    pdf_a4_tag = table_tag.find_all('a',
                                    {'href': re.compile(r'.+pdf-a4\.zip$')})
    for url in pdf_a4_tag:
        if 'Download' in url.text:
            pdf_a4_link = url['href']
            archive_url = urljoin(downloads_url, pdf_a4_link)
            filename = archive_url.split('/')[-1]
            archive_path = downloads_dir / filename
            response = session.get(archive_url)
            with open(archive_path, 'wb') as file:
                file.write(response.content)
    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    response = get_response(session, MAIN_PEP_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    numerical_table_tag = find_tag(soup,
                                   'section',
                                   attrs={'id': 'numerical-index'})
    body_table_tag = find_tag(numerical_table_tag, 'tbody')
    pep_rows = body_table_tag.find_all('tr')
    results = [('Cтатус', 'Количество')]
    count_of_statuses = {}
    for row in tqdm(pep_rows):
        status_on_main_page = find_tag(row, 'td').text[1:]
        pep_a_tag = find_tag(row, 'a')
        pep_link = urljoin(MAIN_PEP_URL, pep_a_tag['href'])
        response = get_response(session, pep_link)
        if response is None:
            continue
        sibling_soup = BeautifulSoup(response.text, 'lxml')
        status_tag = sibling_soup.find(string='Status')
        status_on_peps_page = status_tag.parent.find_next_sibling().text
        count_of_statuses[status_on_peps_page] = count_of_statuses.get(
            status_on_peps_page, 0) + 1
        if status_on_peps_page not in EXPECTED_STATUS[status_on_main_page]:
            logging.info(
                f'Несовпадающие статусы:\n'
                f'{pep_link}\n'
                f'Cтатус в карточке: {status_on_peps_page}\n'
                f'Ожидаемые статусы: {EXPECTED_STATUS[status_on_main_page]}'
            )
    results.extend(count_of_statuses.items())
    results.append(('Total', len(pep_rows)))
    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')
    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')
    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()
    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)
    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
