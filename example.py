#!/usr/bin/python
import datetime
import os
import sys
import time

import urllib3

urllib3.disable_warnings()

import hexoskin.client
import hexoskin.errors


def basic_login():
    """basic example to perform login"""
    # You may create a .hxauth file with name=value pairs, one per line, which
    # will populate the auth config.
    if not os.path.exists('.hxauth'):
        with open('.hxauth', 'w') as f:
            str1 = 'api_key = your_key\n' \
                   'api_secret = your_secret\n' \
                   'auth = user@example.com:passwd\n' \
                   'base_url = https://api.hexoskin.com\n'
            f.write(str1)

    try:
        with open('.hxauth', 'r') as f:
            conf = dict(map(str.strip, l.split('=', 1)) for l in f.readlines() if l and not l.startswith('#'))
    except:
        raise IOError('Unable to parse .hxauth file!  Please verify that the syntax is correct.')

    if conf['api_key'] == 'your_key':
        raise ValueError('Plese fill the file: ".hxauth" with credentials')

    try:
        # try an oauth2 login
        auth = conf.pop('auth')
        username, password = auth.split(':')
        api = hexoskin.client.HexoApi(**conf)
        api.oauth2_get_access_token(username, password)
    except hexoskin.errors.HttpBadRequest as e:
        # HexoAuth login
        api = hexoskin.client.HexoApi(auth=auth, **conf)
    return api


api = basic_login()


def basic_test():
    """Runs through the some basic API operations."""
    # Get the current user's info
    user = api.account.list()[0]
    print("Get current user {user}")

    # # All the users you can see:
    users = api.user.list()
    print(f"List all users. n= {len(users)}")

    # Get a list of resources, datatype for instance.
    datatypes = api.datatype.list()
    print(f"List the first datatypes. n= {len(datatypes)}")

    # You can get the next page.  Now datatypes is 40 items long.
    datatypes.load_next()
    print(f"List datatypes after loading the second page. n= {len(datatypes)}")

    api.datatype.list(limit=45)
    print(f"List datatypes after the n (45) first datatypes. n= {len(datatypes)}")

    # `datatypes` is a ApiResourceList of ApiResourceInstances.  You can
    # `access it like a list:
    print(f'print the first Datatype: {datatypes[0]}')

    # You can delete right from the list!  This would send a delete request to
    # the API except it's not allowed.
    print('Try to delete a datatype')
    try:
        del datatypes[5]
    except hexoskin.errors.HttpMethodNotAllowed as e:
        # All HttpErrors have an ApiResponse object in `response`.  The string
        # representation includes the body so can be quite large but it is often
        # useful.
        print(f"Datatype {datatypes[5]} not deleted. The log message is {e.response}")

    # You can create items. Range for instance:

    start = datetime.datetime.now().timestamp()*api.freq
    new_range = api.range.create(
        {'name': 'Original_range', 'start':start, 'end': start+5000, 'user': user.resource_uri})
    print(f'Result after creating a range: \n  range_info: {new_range}   range_name: {new_range.name}  '
          f' range_user: {new_range.user}')

    # `new_range` is an ApiResourceInstance.  You can modify it in place:
    new_range.name = 'Modified range name'

    # And update the server:
    new_range.update()
    print(f'Result after modyfying a range: \n  range_info: {new_range}   range_name: {new_range.name} '
          f'  range_user: {new_range.user}')
    # And update the server directly in one line:
    new_range.update({'name': 'Remodified range name'})
    print(f'Result after modyfying a range: \n  range_info: {new_range}   range_name: {new_range.name}  '
          f' range_user: {new_range.user}')

    at = api.activitytype.list()
    # And of course, delete it:
    new_range.delete()

    # Note how I can use an ApiResourceInstance as a value here:
    new_range2 = api.range.create(
        {'name': 'Original_range', 'start': start, 'end': start+5000, 'user': user})
    print(f'Result after creating a range: \n  range_info: {new_range2}   range_name: {new_range2.name}  '
          f' range_user: {new_range2.user}')
    new_range2.delete()
    print(f'Result after deleting a range: \n  range_info: {new_range2}   range_name: {new_range2.name} '
          f'  range_user: {new_range2.user}')

    # Get a list all the elements of a query.
    # This call the "next" api address until all the data are downloaded.
    # Note: this will make many fast calls to the api. The api may not allow it.
    # Note: This can create memory issues if more than 1000 values are downloaded. See next example
    datatypes = api.datatype.list().prefetch_all()
    print(f'preteched a total of {len(datatypes)} datatypes')

    # Get a list all the elements of a call through a generator
    # The elements are fetched on the api as needed. This is useful to limit memory usage when
    # more than 1000 values are expected.
    datatypes_ids = []
    for i, a in enumerate(api.datatype.list().iter_all()):
        datatypes_ids.append(a.id)
    print(f'datatypes ids {datatypes_ids}')


class DataPoller(object):
    """An example of an approach for polling for realtime data in a cache-
    friendly fashon."""

    def __init__(self, api, datatypes, **kwargs):
        self.since = 0
        self.window = 256 * 60 * 10
        self.api = api
        self.datatypes = datatypes
        self.filter_args = kwargs

    def poll(self):
        now = int(time.mktime(datetime.datetime.now().timetuple())) * 256
        if now - self.since > self.window:
            self.since = now
        self.filter_args.update({'start': self.since, 'end': self.since + self.window})
        result = self.api.data.list(datatype__in=self.datatypes, **self.filter_args)
        if result:
            self.since = max([max(v)[0] for d, v in result[0].data.items()])
            if len(result[0].data.itervalues().next()) > 1:
                return result[0].data
        return []


def download_raw(format='edf', **kwargs):
    """
    An example of downloading raw data and saving it to disk.
    Args:
        format (): "edf"  or "zip"
        **kwargs (): The arguments to determine the data.  Expected to be record=12345 or
        range=12345 for sane filenames.
    """
    formats = {
        'edf': 'application/x-edf',
        'zip': 'application/octet-stream',
        'csv': 'text/csv'
    }
    fmt = format.lower()
    mimetype = formats[fmt]
    fname0 = '_'.join(f'{k}_{v}' for k, v in kwargs.items())
    fname = f'{fname0}.{fmt}'
    if fmt == 'csv':
        data= api.data.list(kwargs, mimetype)
        with open(fname,  'w') as f:
            for line in data:
                f.write(','.join(line)+'\n')
    else:
        with open(fname,  'wb') as f:
            f.write(api.data.list(kwargs, mimetype))
    print("File written as {}".format(fname))


if __name__ == '__main__':
    basic_test()
