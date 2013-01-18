import cPickle, json
import pycurl, StringIO, urllib

from hexoskin.errors import *


CACHED_API_RESOURCE_LIST = '.api_resource_stash'

class ApiResourceAccessor(object):
    api = None

    def __init__(self, conf, api):
        self.conf = conf
        self.api = api


    def list(self, *args, **kwargs):
        self._verify_call('list', 'get')
        response = self.api.get(self.conf['list_endpoint'], *args, **kwargs)
        return ApiResourceList(response, self)


    def patch(self, *args, **kwargs):
        self._verify_call('list', 'patch')
        return self.api.patch(self.conf['list_endpoint'], *args, **kwargs)


    def get(self, uri):
        self._verify_call('detail', 'get')
        if type(uri) is int or self.conf['list_endpoint'] not in uri:
            uri = '%s%s/' % (self.conf['list_endpoint'], uri)
        response = self.api.get(uri)
        return ApiResourceInstance(response.result, self)


    def create(self, data, *args, **kwargs):
        self._verify_call('list', 'post')
        response = self.api.post(self.conf['list_endpoint'], data, *args, **kwargs)
        return ApiResourceInstance(response.result, self)


    def _verify_call(self, access_type, method):
        if method not in self.conf['allowed_%s_http_methods' % access_type]:
            raise MethodNotAllowed('%s method is not allowed on a %s %s' % (method, self.conf['name'], access_type))


class ApiResourceList(object):

    def __init__(self, response, parent):
        self.parent = parent
        self.response = response
        self.nexturl = None
        self.objects = []
        self._append_response(self.response)


    def next(self):
        if self.nexturl:
            response = self.parent.api.get(self.nexturl)
            self._append_response(response)
        else:
            raise IndexError('List is already at the end.')


    def _append_response(self, response):
        self.nexturl = response.result['meta']['next'] if 'next' in response.result['meta'] else None
        self.objects += self._create_instances(response.result['objects'])
        # self.response.result['objects'] = self._create_instances response.result['objects'])


    def _create_instances(self, obj_list):
        return map(lambda o: ApiResourceInstance(o, self.parent), obj_list)


    def __getitem__(self, key):
        if type(key) is int:
            return self.objects[key]
        else:
            return self.response.result[key]


    def __delitem__(self, key):
        if type(key) is int:
            self.objects[key].delete()
            del self.objects[key]
        else:
            return super(ApiResourceList, self).__delitem__(key)


    def __iter__(self):
        return iter(self.objects)#(v for v in self.objects)


    def __reversed__(self):
        return reversed(self.objects)


    def __len__(self):
        return len(self.objects)



class ApiResourceInstance(object):

    def __init__(self, obj, parent):
        # Skip __setattr__ for this one.
        self.__dict__['fields'] = obj
        self.parent = parent


    def __getattr__(self, name):
        if name in self.fields:
            return self.fields[name]
        raise AttributeError


    def __setattr__(self, name, value):
        if name in self.__dict__['fields']:
            if name in self.parent.api.resources and type(value) is ApiResourceInstance:
                self.fields[name] = value.resource_uri
                print 'setting %s to %s' % (name, value.resource_uri)
            else:
                self.fields[name] = value
        else:
            super(ApiResourceInstance, self).__setattr__(name, value)


    def __str__(self):
        return str(self.fields)


    def update(self, data=None, *args, **kwargs):
        self.parent._verify_call('detail', 'put')
        if data is not None:
            for k,v in data.items():
                setattr(self, k, v)
        response = self.parent.api.put(self.fields['resource_uri'], self.fields, *args, **kwargs)

        if response.result:
            self.fields = response.result.copy()
        else:
            self.fields = dict(self.fields.items() + data.items())


    def delete(self, *args, **kwargs):
        self.parent._verify_call('detail', 'delete')
        response = self.parent.api.delete(self.fields['resource_uri'], *args, **kwargs)
        self.fields = dict((k, None) for k in self.fields.keys())



class ApiHelper(object):
    auth_user = None
    base_url = None
    resource_conf = {}
    resources = {}

    def __init__(self, base_url=None, user_auth=None):
        super(ApiHelper, self).__init__()
        if base_url is not None:
            self.base_url = base_url
        if user_auth is not None:
            self.auth_user = user_auth


    def __getattr__(self, name):
        if len(self.resources) == 0:
            self.build_resources()
        if name in self.resources:
            return self.resources[name]
        if name in self.resource_conf:
            self.resources[name] = ApiResourceAccessor(self.resource_conf[name], self)
            return self.resources[name]
        else:
            raise AttributeError


    def build_resources(self):
        if CACHED_API_RESOURCE_LIST is not None:
            try:
                with open(CACHED_API_RESOURCE_LIST) as f:
                    self.resource_conf = cPickle.load(f)
            except IOError:
                self._fetch_resource_list()
                try:
                    with open(CACHED_API_RESOURCE_LIST, 'w') as f:
                        cPickle.dump(self.resource_conf, f)
                except IOError, e:
                    print "Couldn't write to stash file: %s" % e
        else:
            self._fetch_resource_list()


    def _fetch_resource_list(self):
        resource_list = self.get('/api/v1/').result
        for n,r in resource_list.iteritems():
            self.resource_conf[n] = self.get(r['schema']).result
            self.resource_conf[n]['list_endpoint'] = r['list_endpoint']
            self.resource_conf[n]['name'] = n


    def _request(self, path, data=None, curlOpt=None, auth=None, method='Unknown'):
        s = StringIO.StringIO()

        req = pycurl.Curl()
        req.setopt(pycurl.SSL_VERIFYPEER, False)
        req.setopt(pycurl.WRITEFUNCTION, s.write)
        req.setopt(pycurl.HTTPHEADER, ['Accept: application/json', 'Content-type: application/json'])
        req.setopt(pycurl.FOLLOWLOCATION, 1)
        req.setopt(pycurl.MAXREDIRS, 5)
        req.setopt(pycurl.URL, str(self.base_url + path))

        if auth is not None:
            req.setopt(pycurl.USERPWD, auth)
        elif self.auth_user is not None:
            req.setopt(pycurl.USERPWD, self.auth_user)
        
        if data is not None:
            req.setopt(pycurl.POSTFIELDS, json.dumps(data))

        if curlOpt is not None:
            for opt, val in curlOpt:
                #print "  setting curl option %s to %s" % (opt, val)
                req.setopt(opt, val)

        # print 'Sending request: %s/%s/' % (self.base_url, path)
        req.perform()

        response = ApiResponse(req.getinfo(pycurl.HTTP_CODE), req.getinfo(pycurl.EFFECTIVE_URL), self._method_from_curl_options(curlOpt), s.getvalue())
        if response.status_code >= 400:
            self._throw_http_exception(response)

        return response


    def post(self, path, data=None, auth=None):
        opts = [(pycurl.POST, 1)]
        return self._request(path, data, opts, auth)


    def get(self, path, data=None, auth=None):
        if data:
            path  = '%s?%s' % (path, urllib.urlencode(data))
        return self._request(path, auth=auth)


    def put(self, path, data=None, auth=None):
        opts = [(pycurl.CUSTOMREQUEST, 'PUT')]
        return self._request(path, data, opts, auth)


    def patch(self, path, data=None, auth=None):
        opts = [(pycurl.CUSTOMREQUEST, 'PATCH')]
        return self._request(path, data, opts, auth)


    def delete(self, path, auth=None):
        opts = [(pycurl.CUSTOMREQUEST, 'DELETE')]
        return self._request(path, None, opts, auth)


    def _method_from_curl_options(self, options):
        if options is not None:
            o = dict(options)
            if pycurl.POST in o:
                return 'POST'
            if pycurl.CUSTOMREQUEST in o:
                return o[pycurl.CUSTOMREQUEST]
        return 'GET'


    def _throw_http_exception(self, response):
        if response.status_code == 400:
            raise HttpBadRequest(response)
        if response.status_code == 401:
            raise HttpUnauthorized(response)
        if response.status_code == 403:
            raise HttpForbidden(response)
        if response.status_code == 404:
            raise HttpNotFound(response)
        if response.status_code == 405:
            raise HttpMethodNotAllowed(response)
        if response.status_code == 500:
            raise HttpInternalServerError(response)
        if response.status_code == 501:
            raise HttpNotImplemented(response)
        raise HttpError(response)



class HexoApi(ApiHelper):
    base_url = 'https://api.hexoskin.com'

    def __init__(self, base_url=None, user_auth=None):
        if base_url is not None:
            self.base_url = base_url
        return super(HexoApi, self).__init__(self.base_url, user_auth)



class ApiResponse(object):

    def __init__(self, status_code, url, method, body):
        try:
            self.result = json.loads(body)
        except:
            self.result = body
        self.body = body
        self.status_code = status_code
        self.url = url
        self.method = method

    def success(self):
        200 <= self.status_code < 400

    def __str__(self):
        return '%s %s %s\n%s' % (self.status_code, self.method.ljust(6), self.url, self.result)

