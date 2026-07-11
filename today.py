import datetime
from dateutil import relativedelta
import requests
import os
import base64
from lxml import etree
import time
import hashlib

# Fine-grained personal access token with All Repositories access:
# Account permissions: read:Followers, read:Starring, read:Watching
# Repository permissions: read:Commit statuses, read:Contents, read:Issues, read:Metadata, read:Pull Requests
HEADERS = {'authorization': 'token '+ os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME']
QUERY_COUNT = {'user_getter': 0, 'follower_getter': 0, 'graph_repos_stars': 0, 'recursive_loc': 0, 'graph_commits': 0, 'loc_query': 0}


def daily_readme(birthday):
    """
    Returns the length of time since a given date
    e.g. 'XX years, XX months, XX days'
    """
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}, {} {}, {} {}{}'.format(
        diff.years, 'year' + format_plural(diff.years),
        diff.months, 'month' + format_plural(diff.months),
        diff.days, 'day' + format_plural(diff.days),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else '')


def format_plural(unit):
    return 's' if unit != 1 else ''


def simple_request(func_name, query, variables):
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
    if request.status_code == 200:
        return request
    raise Exception(func_name, ' has failed with a', request.status_code, request.text, QUERY_COUNT)


def graph_repos_stars(count_type, owner_affiliation, cursor=None, accumulated_stars=0):
    query_count('graph_repos_stars')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    if request.status_code == 200:
        repositories = request.json()['data']['user']['repositories']
        if count_type == 'repos':
            return repositories['totalCount']
        elif count_type == 'stars':
            accumulated_stars += stars_counter(repositories['edges'])
            if repositories['pageInfo']['hasNextPage']:
                return graph_repos_stars(count_type, owner_affiliation, repositories['pageInfo']['endCursor'], accumulated_stars)
            return accumulated_stars


def public_stars_count(username):
    """
    Public REST fallback for total stars across owned repositories.
    """
    total_stars = 0
    page = 1
    while True:
        response = requests.get(
            f'https://api.github.com/users/{username}/repos',
            params={'per_page': 100, 'page': page, 'type': 'owner'},
            headers={'Accept': 'application/vnd.github+json'},
            timeout=30,
        )
        if response.status_code != 200:
            break
        repos = response.json()
        if not isinstance(repos, list) or not repos:
            break
        total_stars += sum(repo.get('stargazers_count', 0) for repo in repos)
        if len(repos) < 100:
            break
        page += 1
    return total_stars


def contribution_counter(username, from_date='2019-01-01T00:00:00Z', to_date=None):
    """
    Returns total GitHub contribution count for the user.
    """
    query_count('graph_commits')
    if to_date is None:
        to_date = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    query = '''
    query($login: String!, $from: DateTime!, $to: DateTime!) {
        user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
                contributionCalendar {
                    totalContributions
                }
            }
        }
    }'''
    variables = {'login': username, 'from': from_date, 'to': to_date}
    request = simple_request(contribution_counter.__name__, query, variables)
    return int(request.json()['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions'])


def recursive_loc(owner, repo_name, data, cache_comment, addition_total=0, deletion_total=0, my_commits=0, cursor=None):
    query_count('recursive_loc')
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    ... on Commit {
                                        committedDate
                                    }
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor}
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
    if request.status_code == 200:
        if request.json()['data']['repository']['defaultBranchRef'] != None:
            return loc_counter_one_repo(owner, repo_name, data, cache_comment, request.json()['data']['repository']['defaultBranchRef']['target']['history'], addition_total, deletion_total, my_commits)
        else: return 0
    force_close_file(data, cache_comment)
    if request.status_code == 403:
        raise Exception('Too many requests in a short amount of time!\nYou\'ve hit the non-documented anti-abuse limit!')
    raise Exception('recursive_loc() has failed with a', request.status_code, request.text, QUERY_COUNT)


def loc_counter_one_repo(owner, repo_name, data, cache_comment, history, addition_total, deletion_total, my_commits):
    for node in history['edges']:
        if node['node']['author']['user'] == OWNER_ID:
            my_commits += 1
            addition_total += node['node']['additions']
            deletion_total += node['node']['deletions']

    if history['edges'] == [] or not history['pageInfo']['hasNextPage']:
        return addition_total, deletion_total, my_commits
    else: return recursive_loc(owner, repo_name, data, cache_comment, addition_total, deletion_total, my_commits, history['pageInfo']['endCursor'])


def loc_query(owner_affiliation, comment_size=0, force_cache=False, cursor=None, edges=[]):
    query_count('loc_query')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
            edges {
                node {
                    ... on Repository {
                        nameWithOwner
                        defaultBranchRef {
                            target {
                                ... on Commit {
                                    history {
                                        totalCount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(loc_query.__name__, query, variables)
    if request.json()['data']['user']['repositories']['pageInfo']['hasNextPage']:
        edges += request.json()['data']['user']['repositories']['edges']
        return loc_query(owner_affiliation, comment_size, force_cache, request.json()['data']['user']['repositories']['pageInfo']['endCursor'], edges)
    else:
        return cache_builder(edges + request.json()['data']['user']['repositories']['edges'], comment_size, force_cache)


def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    cached = True
    filename = 'cache/'+hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt'
    try:
        with open(filename, 'r') as f:
            data = f.readlines()
    except FileNotFoundError:
        data = []
        if comment_size > 0:
            for _ in range(comment_size): data.append('This line is a comment block. Write whatever you want here.\n')
        with open(filename, 'w') as f:
            f.writelines(data)

    if len(data)-comment_size != len(edges) or force_cache:
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, 'r') as f:
            data = f.readlines()

    cache_comment = data[:comment_size]
    data = data[comment_size:]
    for index in range(len(edges)):
        repo_hash, commit_count, *__ = data[index].split()
        if repo_hash == hashlib.sha256(edges[index]['node']['nameWithOwner'].encode('utf-8')).hexdigest():
            try:
                history_total = edges[index]['node']['defaultBranchRef']['target']['history']['totalCount']
                if not cached or int(commit_count) != history_total:
                    owner, repo_name = edges[index]['node']['nameWithOwner'].split('/')
                    loc = recursive_loc(owner, repo_name, data, cache_comment)
                    data[index] = repo_hash + ' ' + str(history_total) + ' ' + str(loc[2]) + ' ' + str(loc[0]) + ' ' + str(loc[1]) + '\n'
            except TypeError:
                data[index] = repo_hash + ' 0 0 0 0\n'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    for line in data:
        loc = line.split()
        loc_add += int(loc[3])
        loc_del += int(loc[4])
    return [loc_add, loc_del, loc_add - loc_del, cached]


def flush_cache(edges, filename, comment_size):
    with open(filename, 'r') as f:
        data = []
        if comment_size > 0:
            data = f.readlines()[:comment_size]
    with open(filename, 'w') as f:
        f.writelines(data)
        for node in edges:
            f.write(hashlib.sha256(node['node']['nameWithOwner'].encode('utf-8')).hexdigest() + ' 0 0 0 0\n')


def force_close_file(data, cache_comment):
    filename = 'cache/'+hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    print('There was an error while writing to the cache file. The file,', filename, 'has had the partial data saved and closed.')


def stars_counter(data):
    total_stars = 0
    for node in data: total_stars += node['node']['stargazers']['totalCount']
    return total_stars


def embed_ascii_art(filename):
    """
    GitHub blocks external image URLs inside README SVGs.
    Embed ascii-art.png as a base64 data URI so the portrait renders correctly.
    """
    with open('ascii-art.png', 'rb') as image_file:
        image_data = 'data:image/png;base64,' + base64.b64encode(image_file.read()).decode()

    tree = etree.parse(filename)
    root = tree.getroot()
    image = root.find('.//{http://www.w3.org/2000/svg}image')
    if image is None:
        rect = root.find('.//{http://www.w3.org/2000/svg}rect')
        image = etree.Element('image')
        image.set('x', '15')
        image.set('y', '15')
        image.set('width', '360')
        image.set('height', '447')
        image.set('preserveAspectRatio', 'xMidYMid meet')
        if rect is not None:
            rect.addnext(image)
        else:
            root.insert(0, image)

    image.set('href', image_data)
    if image.get('{http://www.w3.org/1999/xlink}href') is not None:
        image.attrib.pop('{http://www.w3.org/1999/xlink}href', None)
    tree.write(filename, encoding='utf-8', xml_declaration=True)


LABEL_WIDTHS = {
    'mohsen_uptime_data': "Mohsen Uptime",
    'age_data': 'GitHub Uptime',
    'repo_data': 'Repos',
    'contrib_data': 'Repos',
    'star_data': 'Repos',
    'follower_data': 'Followers',
}

LINE_WIDTH = 57


def format_number(value):
    return f"{'{:,}'.format(value)}" if isinstance(value, int) else str(value)


def justify_dots(label_plain, value_text):
    prefix_len = len(f'. {label_plain}:')
    gap = max(1, LINE_WIDTH - prefix_len - len(value_text) - 1)
    return ' ' + ('.' * gap) + ' '


def svg_overwrite(filename, mohsen_uptime_data, age_data, star_data, repo_data, contrib_data, follower_data):
    tree = etree.parse(filename)
    root = tree.getroot()

    find_and_replace(root, 'mohsen_uptime_data', mohsen_uptime_data)
    find_and_replace(root, 'mohsen_uptime_data_dots', justify_dots(LABEL_WIDTHS['mohsen_uptime_data'], mohsen_uptime_data))

    find_and_replace(root, 'age_data', age_data)
    find_and_replace(root, 'age_data_dots', justify_dots(LABEL_WIDTHS['age_data'], age_data))

    repo_data_s = format_number(repo_data)
    contrib_data_s = format_number(contrib_data)
    star_data_s = format_number(star_data)
    repos_line = f'{repo_data_s} {{Contributed: {contrib_data_s}}} | Stars: {star_data_s}'
    find_and_replace(root, 'repo_data', repo_data_s)
    find_and_replace(root, 'contrib_data', contrib_data_s)
    find_and_replace(root, 'star_data', star_data_s)
    find_and_replace(root, 'repos_line_dots', justify_dots('Repos', repos_line))

    follower_data_s = format_number(follower_data)
    find_and_replace(root, 'follower_data', follower_data_s)
    find_and_replace(root, 'follower_data_dots', justify_dots('Followers', follower_data_s))

    tree.write(filename, encoding='utf-8', xml_declaration=True)


def find_and_replace(root, element_id, new_text):
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def commit_counter(comment_size):
    total_commits = 0
    filename = 'cache/'+hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt'
    try:
        with open(filename, 'r') as f:
            data = f.readlines()
    except FileNotFoundError:
        return 0
    cache_comment = data[:comment_size]
    data = data[comment_size:]
    for line in data:
        total_commits += int(line.split()[2])
    return total_commits


def user_getter(username):
    query_count('user_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }'''
    variables = {'login': username}
    request = simple_request(user_getter.__name__, query, variables)
    return {'id': request.json()['data']['user']['id']}, request.json()['data']['user']['createdAt']


def follower_getter(username):
    query_count('follower_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }'''
    request = simple_request(follower_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])


def query_count(funct_id):
    global QUERY_COUNT
    QUERY_COUNT[funct_id] += 1


def perf_counter(funct, *args):
    start = time.perf_counter()
    funct_return = funct(*args)
    return funct_return, time.perf_counter() - start


def formatter(query_type, difference, funct_return=False, whitespace=0):
    print('{:<23}'.format('   ' + query_type + ':'), sep='', end='')
    print('{:>12}'.format('%.4f' % difference + ' s ')) if difference > 1 else print('{:>12}'.format('%.4f' % (difference * 1000) + ' ms'))
    if whitespace:
        return f"{'{:,}'.format(funct_return): <{whitespace}}"
    return funct_return


if __name__ == '__main__':
    print('Calculation times:')
    user_data, user_time = perf_counter(user_getter, USER_NAME)
    OWNER_ID, acc_date = user_data
    formatter('account data', user_time)
    acc_created = datetime.datetime.strptime(acc_date[:10], '%Y-%m-%d')
    mohsen_uptime_data, mohsen_time = perf_counter(daily_readme, datetime.datetime(1997, 4, 29))
    formatter('mohsen uptime', mohsen_time)
    github_uptime_data, age_time = perf_counter(daily_readme, acc_created)
    formatter('github uptime', age_time)
    star_data, star_time = perf_counter(graph_repos_stars, 'stars', ['OWNER'])
    if star_data == 0:
        star_data, star_fallback_time = perf_counter(public_stars_count, USER_NAME)
        star_time += star_fallback_time
    repo_data, repo_time = perf_counter(graph_repos_stars, 'repos', ['OWNER'])
    contrib_data, contrib_time = perf_counter(graph_repos_stars, 'repos', ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'])
    follower_data, follower_time = perf_counter(follower_getter, USER_NAME)

    for svg_file in ('dark_mode.svg', 'light_mode.svg'):
        embed_ascii_art(svg_file)

    svg_overwrite('dark_mode.svg', mohsen_uptime_data, github_uptime_data, star_data, repo_data, contrib_data, follower_data)
    svg_overwrite('light_mode.svg', mohsen_uptime_data, github_uptime_data, star_data, repo_data, contrib_data, follower_data)

    print('\033[F\033[F\033[F\033[F\033[F\033[F\033[F',
        '{:<21}'.format('Total function time:'), '{:>11}'.format('%.4f' % (user_time + mohsen_time + age_time + star_time + repo_time + contrib_time)),
        ' s \033[E\033[E\033[E\033[E\033[E\033[E\033[E\033[E', sep='')

    print('Total GitHub GraphQL API calls:', '{:>3}'.format(sum(QUERY_COUNT.values())))
    for funct_name, count in QUERY_COUNT.items(): print('{:<28}'.format('   ' + funct_name + ':'), '{:>6}'.format(count))
