#!/usr/bin/python
import urllib3
urllib3.disable_warnings()

import hexoskin.client
import hexoskin.errors

# Example of setting a new cache file.
# hexoskin.client.CACHED_API_RESOURCE_LIST = '.new_file'

# You may create a .hxauth file with name=value pairs, one per line, which
# will populate the auth config.  Or you may put default values here if you
# prefer not to create a .hxauth file.
try:
    with open('.hxauth', 'r') as f:
        conf = dict(map(str.strip, l.split('=', 1)) for l in f.readlines() if l and not l.startswith('#'))
except FileNotFoundError:
    conf = {
        'api_key': 'your key',
        'api_secret': 'your secret',
        'auth': 'user@example.com:passwd',
        # 'api_version': 'latest',
    }
except:
    print('Unable to parse .hxauth file!  Please verify that the syntax is correct.')
    sys.exit(1)


# Override input in Python 2.
try: input = raw_input
except: pass


api = hexoskin.client.HexoApi(**conf)


def basic_test():
    """Runs through the some basic API operations."""
    try:
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
        except hexoskin.errors.MethodNotAllowed as e:
            print("Oh no you di'nt! %s" % e)

        # You can create items, a Range for instance:
        new_range = api.range.create({'name':'testnew_range', 'start':353163129199, 'end':353163139199, 'user':user.resource_uri})

        # `new_range` is an ApiResourceInstance.  You can modify it in place:
        new_range.name = 'newtestyrangey'

        # And update the server:
        new_range.update()
        print(new_range)

        # Or by passing a dictionary to update(), note how I can use an
        # ApiResourceInstance as a value here.  That works with the assignment
        # method above too:
        new_range.update({'user': users[0]})
        print(new_range)

        # And of course, delete it:
        new_range.delete()

    except hexoskin.errors.HttpError as e:
        # All HttpErrors have an ApiResponse object in `response`.  The string
        # representation includes the body so can be quite large but it is often
        # useful.
        print(e.response)

    except hexoskin.errors.MethodNotAllowed as e:
        # Requests are verified client-side before being sent.  If you try to use
        # a method that's not allowed, a MethodNotAllowed exception is raised.
        print("You can't do that! %s" % e)


class DataPoller(object):
    """An example of an approach for polling for realtime data in a cache-
    friendly fashon."""

    def __init__(self, api, datatypes, **kwargs):
        self.since = 0
        self.window = 256*60*10
        self.api = api
        self.datatypes = datatypes
        self.filter_args = kwargs

    def poll(self):
        now = int(time.mktime(datetime.datetime.now().timetuple())) * 256
        if now - self.since > self.window:
            self.since = now
        self.filter_args.update({'start': self.since, 'end': self.since+self.window})
        result = self.api.data.list(datatype__in=self.datatypes, **self.filter_args)
        if result:
            self.since = max([max(v)[0] for d,v in result[0].data.items()])
            if len(result[0].data.itervalues().next()) > 1:
                return result[0].data
        return []


def download_raw(**kwargs):
    """An example of downloading raw data and saving it to disk.

    \param kwargs The arguments to determine the data.  Expected to be record=12345 or
        range=12345 for sane filenames.
    """
    # qry = sys.argv[1]
    formats = {
        'edf': 'application/x-edf',
        'zip': 'application/octet-stream',
    }
    fmt = kwargs.pop('format', 'edf').lower()
    mimetype = formats[fmt]
    fname = '{}.{}'.format('_'.join('{}_{}'.format(k,v) for k,v in kwargs.items()), fmt)
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
