#!/usr/bin/python
import urllib3
import sys
import time
import datetime
import os
urllib3.disable_warnings()

import hexoskin.client
import hexoskin.errors

if sys.version_info[0] < 3:
    input = raw_input


# Example of setting a new cache file.
# hexoskin.client.CACHED_API_RESOURCE_LIST = '.new_file'

# You may create a .hxauth file with name=value pairs, one per line, which
# will populate the auth config.
if not os.path.exists('.hxauth'):
    with open('.hxauth', 'w') as f:
        f.write('api_key = your_key\n'
                'api_secret = your_secret\n'
                'auth = user@example.com:passwd\n',
                'base_url = https://api.hexoskin.com\n')

try:
    with open('.hxauth', 'r') as f:
        conf = dict(map(str.strip, l.split('=', 1)) for l in f.readlines() if l and not l.startswith('#'))
except:
    raise IOError('Unable to parse .hxauth file!  Please verify that the syntax is correct.')

if conf['api_key'] == 'your_key':
    raise ValueError('Plese fill the file: ".hxauth" with credentials')


api = hexoskin.client.HexoApi(**conf)


def basic_test():
    """Runs through the some basic API operations."""
    # Get the current user's info
    user = api.account.list()[0]
    print(user)

    # # All the users you can see:
    users = api.user.list()
    print(users[0])

    # Get a list of resources, datatype for instance.
    datatypes = api.datatype.list()

    # `datatypes` is a ApiResourceList of ApiResourceInstances.  You can
    # `access it like a list:
    print(datatypes[0])

    # You can get the next page.  Now datatypes is 40 items long.
    datatypes.load_next()

    # You can delete right from the list!  This would send a delete request to
    # the API except it's not allowed.

    try:
        del datatypes[5]
    except hexoskin.errors.HttpMethodNotAllowed as e:
        print("range not deleted: {}".format(datatypes[5]))

        # All HttpErrors have an ApiResponse object in `response`.  The string
        # representation includes the body so can be quite large but it is often
        # useful.
        print(e.response)




    # You can create items, a Range for instance:
    new_range = api.range.create(
        {'name': 'testnew_range', 'start': 353163129199, 'end': 353163139199, 'user': user.resource_uri})
    print(new_range, new_range.name, new_range.user)

    # `new_range` is an ApiResourceInstance.  You can modify it in place:
    new_range.name = 'newtestyrangey'

    # And update the server:
    new_range.update()
    print(new_range, new_range.name, new_range.user)

    # Or by passing a dictionary to update(), note how I can use an
    # ApiResourceInstance as a value here.  That works with the assignment
    # method above too:
    new_range.update({'user': users[0]})
    print(new_range, new_range.name, new_range.user)

    # And of course, delete it:
    new_range.delete()


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


def download_raw(**kwargs):
    """An example of downloading raw data and saving it to disk.

    \param kwargs The arguments to determine the data.  Expected to be record=12345 or
        range=12345 for sane filenames.
    """
    formats = {
        'edf': 'application/x-edf',
        'zip': 'application/octet-stream',
    }
    fmt = kwargs.pop('format', 'edf').lower()
    mimetype = formats[fmt]
    fname = '{}.{}'.format('_'.join('{}_{}'.format(k, v) for k, v in kwargs.items()), fmt)
    api.oauth2_get_access_token(*conf['auth'].split(':', 1))
    with open(fname, 'wb') as f:
        f.write(api.data.list(kwargs, mimetype))
    print("File written as {}".format(fname))


def oauth2_authorization_code(redirect_uri='https://www.example.com/'):
    auth_url = api.oauth2_get_request_token_url(redirect_uri)
    token_url = input('Go to:\n\n{}\n\nPaste the resulting redirect URL here:'.format(auth_url))
    if token_url:
        api.oauth2_get_access_token(token_url)
        return api.account.list()


if __name__ == '__main__':
    basic_test()
